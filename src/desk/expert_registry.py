"""The Desk-wide expert registry (TODO c2555b5): who can be asked what, the
questions put to them, and the answers -- kept in a local PostgreSQL database
because an answer can take minutes to days to arrive, long after the asking
session is gone. See plans/expert-registry.md.

Postgres is reached the way the user's other projects do (`../world-timelines`,
`../inadvisable-archive`): no driver dependency, just the `psql` CLI against a
self-contained cluster on a unix socket (no TCP port). The cluster is Desk-wide
(`~/.desk/experts/pgdata`, database `desk_experts`), created and started lazily
on first use, and left running afterwards. Every statement is sent on stdin with
`:'name'` variable interpolation (psql's own literal quoting) and returns one
JSON value, so no SQL is ever built from strings.

Qt-free and thread-safe (one lock around provisioning), used from the MCP
server's thread, the Bridge's thread and the GUI thread alike.

The asker's private `note_to_self` is stored with the question but is returned
only when `include_note=True` (the asker's own view and the agent handoff);
every expert-side read leaves it out.
"""

import json
import os
import re
import shutil
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path

EXPERTS_CHANGED_EVENT = "desk.experts.changed"
DEFAULT_PGDATA = Path.home() / ".desk" / "experts" / "pgdata"
DBNAME = "desk_experts"
DESK_EXPERT_ID = "desk"  # questions about Desk itself; a local Claude (Desk) session answers if nobody does
FALLBACK_ACCEPTED_BY = "desk-fallback"
FALLBACK_AFTER_SECONDS = 20
USER_EXPERT_ID = "user"  # the built-in human expert, answered through the Experts widget
KINDS = ("human", "hmsvc", "agent")
STATUSES = ("open", "accepted", "answered", "withdrawn")
REPORT_STATUSES = ("new", "accepted", "rejected", "duplicate", "integrated")
REVIEW_DECISIONS = ("accepted", "rejected", "duplicate")
OPEN_REPORT_STATUSES = ("new", "accepted")
OPEN_STATUSES = ("open", "accepted")
EXPERT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
MAX_TEXT_CHARS = 20000
# A Desk is considered running while its notifier has checked in this recently (a few 10s polls).
PRESENCE_TTL_SECONDS = 35
_KEG_VERSIONS = ("18", "17", "16", "15", "14")

NO_POSTGRES_MESSAGE = (
    "PostgreSQL was not found, so the expert registry is unavailable. Install it (for example "
    "`brew install postgresql@18`) or point DESK_PG_BIN at a directory containing psql, initdb and pg_ctl."
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS experts (
  expert_id     text PRIMARY KEY,
  name          text NOT NULL,
  description   text NOT NULL DEFAULT '',
  kind          text NOT NULL CHECK (kind IN ('human', 'hmsvc', 'agent')),
  registered_by text NOT NULL DEFAULT '',
  registered_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE experts ADD COLUMN IF NOT EXISTS listens_for text NOT NULL DEFAULT '';
CREATE TABLE IF NOT EXISTS expert_questions (
  question_id        text PRIMARY KEY DEFAULT left(replace(gen_random_uuid()::text, '-', ''), 12),
  expert_id          text NOT NULL REFERENCES experts (expert_id) ON DELETE CASCADE,
  asker              text NOT NULL DEFAULT '',
  question           text NOT NULL,
  note_to_self       text NOT NULL DEFAULT '',
  status             text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'accepted', 'answered', 'withdrawn')),
  accepted_by        text,
  answer             text,
  answered_by        text,
  asked_at           timestamptz NOT NULL DEFAULT now(),
  answered_at        timestamptz,
  answer_notified_at timestamptz,
  expert_notified_at timestamptz,
  handed_off_at      timestamptz,
  origin             text NOT NULL DEFAULT ''
);
ALTER TABLE expert_questions ADD COLUMN IF NOT EXISTS origin text NOT NULL DEFAULT '';
CREATE TABLE IF NOT EXISTS expert_reports (
  report_id          text PRIMARY KEY DEFAULT left(replace(gen_random_uuid()::text, '-', ''), 12),
  expert_id          text NOT NULL REFERENCES experts (expert_id) ON DELETE CASCADE,
  reporter           text NOT NULL DEFAULT '',
  title              text NOT NULL,
  finding            text NOT NULL,
  evidence           text NOT NULL DEFAULT '',
  status             text NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'accepted', 'rejected', 'duplicate', 'integrated')),
  reviewed_by        text,
  review_note        text,
  integration_note   text,
  integrated_by      text,
  reported_at        timestamptz NOT NULL DEFAULT now(),
  reviewed_at        timestamptz,
  integrated_at      timestamptz,
  origin             text NOT NULL DEFAULT '',
  expert_notified_at timestamptz,
  outcome_notified_at timestamptz
);
CREATE INDEX IF NOT EXISTS expert_reports_status_idx ON expert_reports (status, reported_at);
CREATE TABLE IF NOT EXISTS desk_presence (
  origin  text PRIMARY KEY,
  seen_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS expert_questions_status_idx ON expert_questions (status, asked_at);
INSERT INTO experts (expert_id, name, description, kind, registered_by)
VALUES ('user', 'You', 'The person using this Desk; questions are answered in the Experts widget.', 'human', 'desk')
ON CONFLICT (expert_id) DO NOTHING;
INSERT INTO experts (expert_id, name, description, kind, registered_by)
VALUES ('desk', 'Desk', 'Questions about Desk itself or the running Desk session. If nobody answers within about 20 seconds, Desk starts a local Claude (Desk) session that reads its own source and docs and answers.', 'agent', 'desk')
ON CONFLICT (expert_id) DO NOTHING;
UPDATE experts SET listens_for = 'Findings about how Desk itself behaves: quirks, undocumented behavior, workarounds that worked, things the docs get wrong.'
WHERE expert_id = 'desk' AND registered_by = 'desk' AND listens_for = '';
"""

_EXPERT_COLUMNS = "expert_id, name, description, kind, registered_by, registered_at, listens_for"
_REPORT_COLUMNS = (
    "report_id, expert_id, reporter, title, finding, evidence, status, reviewed_by, review_note, "
    "integration_note, integrated_by, reported_at, reviewed_at, integrated_at"
)
_PUBLIC_COLUMNS = (
    "question_id, expert_id, asker, question, status, accepted_by, answer, answered_by, "
    "asked_at, answered_at, handed_off_at"
)


class ExpertRegistryError(Exception):
    """Something the caller can act on: bad input, an unknown id, no Postgres."""


def find_pg_bin() -> Path | None:
    """The directory holding psql/initdb/pg_ctl, or None."""
    candidates: list[Path] = []
    if os.environ.get("DESK_PG_BIN"):
        candidates.append(Path(os.environ["DESK_PG_BIN"]))
    candidates += [Path(f"/opt/homebrew/opt/postgresql@{v}/bin") for v in _KEG_VERSIONS]
    on_path = shutil.which("pg_ctl")
    if on_path:
        candidates.append(Path(on_path).parent)
    for directory in candidates:
        if all((directory / tool).exists() for tool in ("psql", "initdb", "pg_ctl")):
            return directory
    return None


class ExpertRegistry:
    def __init__(self, pgdata: Path | None = None, dbname: str = DBNAME, pg_bin: Path | None = None) -> None:
        self.pgdata = Path(pgdata) if pgdata is not None else DEFAULT_PGDATA
        self.dbname = dbname
        self._pg_bin = pg_bin
        self._lock = threading.Lock()
        self._ready = False
        self._listeners: list[Callable[[str, str], None]] = []

    # -- change notification ----------------------------------------------

    def add_listener(self, listener: Callable[[str, str], None]) -> None:
        """`listener(kind, id)` after a registry change ("expert"/"question")."""
        self._listeners.append(listener)

    def _changed(self, kind: str, ident: str) -> None:
        for listener in list(self._listeners):
            try:
                listener(kind, ident)
            except Exception:  # a listener must never break a registry call
                pass

    # -- provisioning -----------------------------------------------------

    def cluster_exists(self) -> bool:
        return (self.pgdata / "PG_VERSION").is_file()

    def _bin(self, tool: str) -> str:
        directory = self._pg_bin or find_pg_bin()
        if directory is None:
            raise ExpertRegistryError(NO_POSTGRES_MESSAGE)
        self._pg_bin = directory
        return str(directory / tool)

    @staticmethod
    def _run(args: list[str], stdin: str | None = None, check: bool = True) -> subprocess.CompletedProcess:
        result = subprocess.run(args, input=stdin, capture_output=True, text=True)
        if check and result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise ExpertRegistryError(f"{Path(args[0]).name} failed: {detail}")
        return result

    def _is_running(self) -> bool:
        return self._run([self._bin("pg_isready"), "-h", str(self.pgdata)], check=False).returncode == 0

    def ensure(self) -> None:
        """Creates/starts the cluster and database and applies the schema.
        Safe to call repeatedly; cheap once done."""
        with self._lock:
            if self._ready:
                return
            self._bin("psql")  # fail early with the install hint
            self.pgdata.parent.mkdir(parents=True, exist_ok=True)
            if not self.cluster_exists():
                base = [self._bin("initdb"), "-D", str(self.pgdata), "-E", "UTF8", "-A", "trust"]
                if self._run(base + ["--locale=en_US.UTF-8"], check=False).returncode != 0:
                    shutil.rmtree(self.pgdata, ignore_errors=True)
                    self._run(base + ["--no-locale"])
            if not self._is_running():
                self._run(
                    [self._bin("pg_ctl"), "-D", str(self.pgdata), "-l", str(self.pgdata / "postgres.log"),
                     "-o", f"-k {self.pgdata} -h ''", "-w", "start"]
                )
            exists = self._run(
                [self._bin("psql"), "-X", "-q", "-A", "-t", "-h", str(self.pgdata), "-d", "postgres",
                 "-c", f"SELECT 1 FROM pg_database WHERE datname = '{self.dbname}'"]
            ).stdout.strip()
            if not exists:
                self._run([self._bin("createdb"), "-h", str(self.pgdata), self.dbname])
            self._exec(SCHEMA)
            self._ready = True

    def stop(self) -> None:
        """Stops the cluster (tests; Desk itself leaves it running)."""
        with self._lock:
            self._ready = False
            if self.cluster_exists():
                self._run([self._bin("pg_ctl"), "-D", str(self.pgdata), "-m", "fast", "stop"], check=False)

    # -- SQL plumbing -----------------------------------------------------

    def _exec(self, sql: str, **variables: str) -> str:
        args = [self._bin("psql"), "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-h", str(self.pgdata), "-d", self.dbname]
        for name, value in variables.items():
            args += ["-v", f"{name}={value}"]
        args += ["-f", "-"]
        return self._run(args, stdin=sql).stdout

    def _json(self, sql: str, **variables: str):
        self.ensure()
        try:
            out = self._exec(sql, **variables)
        except ExpertRegistryError as e:
            if "connect" not in str(e).lower():
                raise
            # The cluster went away since it was provisioned (a reboot, a manual stop): bring it back once.
            self._ready = False
            self.ensure()
            out = self._exec(sql, **variables)
        out = out.strip()
        return json.loads(out) if out else None

    # -- validation -------------------------------------------------------

    @staticmethod
    def _text(value: object, field: str, required: bool = True) -> str:
        if not isinstance(value, str):
            raise ExpertRegistryError(f"{field} must be a string.")
        value = value.strip()
        if required and not value:
            raise ExpertRegistryError(f"{field} must not be empty.")
        if len(value) > MAX_TEXT_CHARS:
            raise ExpertRegistryError(f"{field} is longer than {MAX_TEXT_CHARS} characters.")
        if "\0" in value:
            raise ExpertRegistryError(f"{field} contains a NUL character.")
        return value

    @staticmethod
    def _expert_id(value: object) -> str:
        if not isinstance(value, str) or not EXPERT_ID_PATTERN.match(value.strip()):
            raise ExpertRegistryError(
                "expert_id must be 1-64 characters: lowercase letters, digits, '.', '_' or '-', starting with a letter or digit."
            )
        return value.strip()

    # -- experts ----------------------------------------------------------

    def list_experts(self) -> list[dict]:
        return self._json(
            "SELECT coalesce(json_agg(e ORDER BY e.registered_at, e.expert_id), '[]'::json) "
            f"FROM (SELECT {_EXPERT_COLUMNS} FROM experts) e;"
        )

    def get_expert(self, expert_id: str) -> dict | None:
        rows = self._json(
            f"SELECT coalesce(json_agg(e), '[]'::json) FROM (SELECT {_EXPERT_COLUMNS} FROM experts WHERE expert_id = :'id') e;",
            id=self._expert_id(expert_id),
        )
        return rows[0] if rows else None

    def register_expert(self, expert_id: str, name: str, description: str = "", kind: str = "agent", registered_by: str = "",
                        listens_for: str = "") -> dict:
        """Registers or updates an expert. The built-in `user` expert cannot be
        changed, and an expert can only be updated by whoever registered it."""
        expert_id = self._expert_id(expert_id)
        name = self._text(name, "name")
        description = self._text(description, "description", required=False)
        registered_by = self._text(registered_by, "registered_by", required=False)
        listens_for = self._text(listens_for, "listens_for", required=False)
        if kind not in KINDS:
            raise ExpertRegistryError(f"kind must be one of {', '.join(KINDS)}.")
        existing = self.get_expert(expert_id)
        if existing is not None:
            if expert_id == USER_EXPERT_ID:
                raise ExpertRegistryError("The built-in 'user' expert cannot be changed.")
            if existing["registered_by"] != registered_by:
                raise ExpertRegistryError(f"Expert {expert_id!r} was registered by someone else and cannot be changed from here.")
        rows = self._json(
            "WITH r AS (INSERT INTO experts (expert_id, name, description, kind, registered_by, listens_for) "
            "VALUES (:'id', :'name', :'description', :'kind', :'by', :'listens') "
            "ON CONFLICT (expert_id) DO UPDATE SET name = EXCLUDED.name, description = EXCLUDED.description, "
            "kind = EXCLUDED.kind, listens_for = EXCLUDED.listens_for "
            f"RETURNING {_EXPERT_COLUMNS}) "
            "SELECT coalesce(json_agg(r), '[]'::json) FROM r;",
            id=expert_id, name=name, description=description, kind=kind, by=registered_by, listens=listens_for,
        )
        self._changed("expert", expert_id)
        return rows[0]

    # -- questions --------------------------------------------------------

    def _question_rows(self, where: str, include_note: bool, limit: int = 200, **variables: str) -> list[dict]:
        columns = _PUBLIC_COLUMNS + (", note_to_self" if include_note else "")
        return self._json(
            f"SELECT coalesce(json_agg(q), '[]'::json) FROM (SELECT {columns} FROM expert_questions "
            f"WHERE {where} ORDER BY asked_at DESC, question_id LIMIT {int(limit)}) q;",
            **variables,
        )

    def get_question(self, question_id: str, include_note: bool = False) -> dict | None:
        rows = self._question_rows("question_id = :'qid'", include_note, qid=self._text(question_id, "question_id"))
        return rows[0] if rows else None

    def list_questions(self, expert_id: str | None = None, statuses: tuple[str, ...] | list[str] | None = None,
                       include_note: bool = False, limit: int = 200) -> list[dict]:
        clauses, variables = ["true"], {}
        if expert_id is not None:
            clauses.append("expert_id = :'eid'")
            variables["eid"] = self._expert_id(expert_id)
        if statuses:
            bad = [s for s in statuses if s not in STATUSES]
            if bad:
                raise ExpertRegistryError(f"status must be one of {', '.join(STATUSES)}.")
            clauses.append("status IN (" + ", ".join(f"'{s}'" for s in statuses) + ")")
        return self._question_rows(" AND ".join(clauses), include_note, limit, **variables)

    def ask(self, expert_id: str, question: str, asker: str = "", note_to_self: str = "", origin: str = "") -> dict:
        expert_id = self._expert_id(expert_id)
        question = self._text(question, "question")
        asker = self._text(asker, "asker", required=False)
        note = self._text(note_to_self, "note_to_self", required=False)
        origin = self._text(origin, "origin", required=False)
        if self.get_expert(expert_id) is None:
            known = ", ".join(e["expert_id"] for e in self.list_experts()) or "(none)"
            raise ExpertRegistryError(f"No expert {expert_id!r}. Registered experts: {known}.")
        rows = self._json(
            "WITH r AS (INSERT INTO expert_questions (expert_id, asker, question, note_to_self, origin) "
            "VALUES (:'eid', :'asker', :'question', :'note', :'origin') RETURNING " + _PUBLIC_COLUMNS + ") "
            "SELECT coalesce(json_agg(r), '[]'::json) FROM r;",
            eid=expert_id, asker=asker, question=question, note=note, origin=origin,
        )
        self._changed("question", rows[0]["question_id"])
        return rows[0]

    def _transition(self, question_id: str, sets: str, allowed: tuple[str, ...], verb: str, **variables: str) -> dict:
        question_id = self._text(question_id, "question_id")
        states = ", ".join(f"'{s}'" for s in allowed)
        rows = self._json(
            f"WITH r AS (UPDATE expert_questions SET {sets} WHERE question_id = :'qid' AND status IN ({states}) "
            f"RETURNING {_PUBLIC_COLUMNS}) SELECT coalesce(json_agg(r), '[]'::json) FROM r;",
            qid=question_id, **variables,
        )
        if not rows:
            current = self.get_question(question_id)
            if current is None:
                raise ExpertRegistryError(f"No question {question_id!r}.")
            raise ExpertRegistryError(f"Question {question_id!r} is {current['status']}; it cannot be {verb}.")
        self._changed("question", question_id)
        return rows[0]

    def accept(self, question_id: str, accepted_by: str = "") -> dict:
        return self._transition(
            question_id, "status = 'accepted', accepted_by = :'by'", ("open",), "accepted",
            by=self._text(accepted_by, "accepted_by", required=False),
        )

    def answer(self, question_id: str, answer: str, answered_by: str = "") -> dict:
        return self._transition(
            question_id, "status = 'answered', answer = :'answer', answered_by = :'by', answered_at = now()",
            ("open", "accepted"), "answered",
            answer=self._text(answer, "answer"), by=self._text(answered_by, "answered_by", required=False),
        )

    def withdraw(self, question_id: str) -> dict:
        return self._transition(question_id, "status = 'withdrawn'", ("open", "accepted"), "withdrawn")

    def mark_handed_off(self, question_id: str) -> None:
        self._json(
            "WITH r AS (UPDATE expert_questions SET handed_off_at = now() WHERE question_id = :'qid' RETURNING 1) "
            "SELECT coalesce(json_agg(r), '[]'::json) FROM r;",
            qid=self._text(question_id, "question_id"),
        )
        self._changed("question", question_id)

    # -- what the notifier still has to announce --------------------------

    # -- reports: findings agents send to listening experts (TODO 0f506f7) --

    def listening_experts(self) -> list[dict]:
        return [e for e in self.list_experts() if e.get("listens_for")]

    def report(self, expert_id: str, title: str, finding: str, evidence: str = "", reporter: str = "", origin: str = "") -> dict:
        """Files a finding with an expert that has said what it listens for. Never waits for a review."""
        expert_id = self._expert_id(expert_id)
        title = self._text(title, "title")
        finding = self._text(finding, "finding")
        evidence = self._text(evidence, "evidence", required=False)
        reporter = self._text(reporter, "reporter", required=False)
        origin = self._text(origin, "origin", required=False)
        expert = self.get_expert(expert_id)
        if expert is None:
            known = ", ".join(e["expert_id"] for e in self.list_experts()) or "(none)"
            raise ExpertRegistryError(f"No expert {expert_id!r}. Registered experts: {known}.")
        if not expert.get("listens_for"):
            listening = "; ".join(f"{e['expert_id']} ({e['listens_for']})" for e in self.listening_experts()) or "(none)"
            raise ExpertRegistryError(
                f"Expert {expert_id!r} is not listening for reports. Experts that are: {listening}."
            )
        rows = self._json(
            "WITH r AS (INSERT INTO expert_reports (expert_id, reporter, title, finding, evidence, origin) "
            "VALUES (:'eid', :'reporter', :'title', :'finding', :'evidence', :'origin') RETURNING " + _REPORT_COLUMNS + ") "
            "SELECT coalesce(json_agg(r), '[]'::json) FROM r;",
            eid=expert_id, reporter=reporter, title=title, finding=finding, evidence=evidence, origin=origin,
        )
        self._changed("report", rows[0]["report_id"])
        return rows[0]

    def get_report(self, report_id: str) -> dict | None:
        rows = self._json(
            f"SELECT coalesce(json_agg(r), '[]'::json) FROM (SELECT {_REPORT_COLUMNS} FROM expert_reports "
            "WHERE report_id = :'rid') r;",
            rid=self._text(report_id, "report_id"),
        )
        return rows[0] if rows else None

    def list_reports(self, expert_id: str | None = None, statuses: tuple[str, ...] | list[str] | None = None,
                     limit: int = 200) -> list[dict]:
        clauses, variables = ["true"], {}
        if expert_id is not None:
            clauses.append("expert_id = :'eid'")
            variables["eid"] = self._expert_id(expert_id)
        if statuses:
            bad = [x for x in statuses if x not in REPORT_STATUSES]
            if bad:
                raise ExpertRegistryError(f"status must be one of {', '.join(REPORT_STATUSES)}.")
            clauses.append("status IN (" + ", ".join(f"'{x}'" for x in statuses) + ")")
        return self._json(
            f"SELECT coalesce(json_agg(r), '[]'::json) FROM (SELECT {_REPORT_COLUMNS} FROM expert_reports "
            f"WHERE {' AND '.join(clauses)} ORDER BY reported_at DESC, report_id LIMIT {int(limit)}) r;",
            **variables,
        )

    def _report_transition(self, report_id: str, sets: str, verb: str, **variables: str) -> dict:
        report_id = self._text(report_id, "report_id")
        states = ", ".join(f"'{x}'" for x in OPEN_REPORT_STATUSES)
        rows = self._json(
            f"WITH r AS (UPDATE expert_reports SET {sets} WHERE report_id = :'rid' AND status IN ({states}) "
            f"RETURNING {_REPORT_COLUMNS}) SELECT coalesce(json_agg(r), '[]'::json) FROM r;",
            rid=report_id, **variables,
        )
        if not rows:
            current = self.get_report(report_id)
            if current is None:
                raise ExpertRegistryError(f"No report {report_id!r}.")
            raise ExpertRegistryError(f"Report {report_id!r} is {current['status']}; it cannot be {verb}.")
        self._changed("report", report_id)
        return rows[0]

    def review_report(self, report_id: str, decision: str, note: str = "", reviewed_by: str = "") -> dict:
        """The expert's evaluation of a `new` (or already `accepted`) report: accepted (worth keeping, not
        folded in yet), rejected, or duplicate. A note is required for rejected/duplicate so the reporter learns why."""
        if decision not in REVIEW_DECISIONS:
            raise ExpertRegistryError(f"decision must be one of {', '.join(REVIEW_DECISIONS)}.")
        note = self._text(note, "note", required=decision != "accepted")
        return self._report_transition(
            report_id, "status = :'decision', review_note = :'note', reviewed_by = :'by', reviewed_at = now()", "reviewed",
            decision=decision, note=note, by=self._text(reviewed_by, "reviewed_by", required=False),
        )

    def integrate_report(self, report_id: str, integration_note: str, integrated_by: str = "") -> dict:
        """Records that the finding has been folded into what the expert knows or maintains; the note says
        where or how, so the reporter (and later readers) can find it."""
        return self._report_transition(
            report_id,
            "status = 'integrated', integration_note = :'note', integrated_by = :'by', integrated_at = now(), "
            "reviewed_at = coalesce(reviewed_at, now())",
            "integrated",
            note=self._text(integration_note, "integration_note"), by=self._text(integrated_by, "integrated_by", required=False),
        )

    def heartbeat(self, origin: str) -> None:
        """Records that the Desk at `origin` (its directory) is running right now."""
        self._json(
            "WITH r AS (INSERT INTO desk_presence (origin, seen_at) VALUES (:'origin', now()) "
            "ON CONFLICT (origin) DO UPDATE SET seen_at = now() RETURNING 1) "
            "SELECT coalesce(json_agg(r), '[]'::json) FROM r;",
            origin=self._text(origin, "origin", required=False),
        )

    def claim_announcements(self, origin: str) -> list[dict]:
        """Atomically takes the announcements the Desk at `origin` should show, stamping each as announced in
        the same statement so two Desks polling together can never both show one. That Desk's own answers
        (and questions for the built-in `user`) come first; a question with no origin, or whose asking Desk
        has not checked in lately (closed), is claimed by whichever Desk polls first. Returns
        [{"kind": "answer" | "question", "question": {...}}], never including the private note."""
        origin = self._text(origin, "origin", required=False)
        mine = (
            "(origin = '' OR origin = :'origin' OR NOT EXISTS (SELECT 1 FROM desk_presence p WHERE "
            f"p.origin = expert_questions.origin AND p.seen_at > now() - interval '{int(PRESENCE_TTL_SECONDS)} seconds'))"
        )
        found: list[dict] = []
        for kind, column, condition, extra in (
            ("answer", "answer_notified_at", "status = 'answered' AND answer_notified_at IS NULL", {}),
            ("question", "expert_notified_at", "status = 'open' AND expert_id = :'eid' AND expert_notified_at IS NULL",
             {"eid": USER_EXPERT_ID}),
        ):
            rows = self._json(
                f"WITH r AS (UPDATE expert_questions SET {column} = now() WHERE {condition} AND {mine} "
                f"RETURNING {_PUBLIC_COLUMNS}) SELECT coalesce(json_agg(r), '[]'::json) FROM r;",
                origin=origin, **extra,
            )
            found += [{"kind": kind, "question": row} for row in rows]
        return found

    def claim_report_announcements(self, origin: str) -> list[dict]:
        """Like claim_announcements, for reports (TODO a63e115): new reports to the experts the person answers
        for (`user`, `desk`) -- shown by the reporting Desk -- and the final outcome (rejected, duplicate or
        integrated) of a report, shown by the Desk that reported it. Each is stamped in the claiming statement.
        Returns [{"kind": "report" | "report_outcome", "report": {...}}]."""
        origin = self._text(origin, "origin", required=False)
        mine = (
            "(origin = '' OR origin = :'origin' OR NOT EXISTS (SELECT 1 FROM desk_presence p WHERE "
            f"p.origin = expert_reports.origin AND p.seen_at > now() - interval '{int(PRESENCE_TTL_SECONDS)} seconds'))"
        )
        found: list[dict] = []
        for kind, column, condition in (
            ("report", "expert_notified_at",
             "status = 'new' AND expert_id IN ('user', 'desk') AND expert_notified_at IS NULL"),
            ("report_outcome", "outcome_notified_at",
             "status IN ('rejected', 'duplicate', 'integrated') AND outcome_notified_at IS NULL"),
        ):
            rows = self._json(
                f"WITH r AS (UPDATE expert_reports SET {column} = now() WHERE {condition} AND {mine} "
                f"RETURNING {_REPORT_COLUMNS}) SELECT coalesce(json_agg(r), '[]'::json) FROM r;",
                origin=origin,
            )
            found += [{"kind": kind, "report": row} for row in rows]
        return found

    def claim_fallback(self, origin: str, question_id: str = "", min_age_seconds: float = FALLBACK_AFTER_SECONDS) -> list[dict]:
        """Atomically takes the still-open questions to the built-in `desk` expert that the Desk at `origin`
        should answer itself -- asked from that Desk (or with no recorded Desk) at least `min_age_seconds` ago
        -- marking each accepted by "desk-fallback" so nobody else picks it up. A question someone has
        already accepted is left alone. `question_id` limits the claim to one question."""
        rows = self._json(
            "WITH r AS (UPDATE expert_questions SET status = 'accepted', accepted_by = :'by' "
            "WHERE expert_id = :'eid' AND status = 'open' AND (origin = '' OR origin = :'origin') "
            "AND asked_at <= now() - (:'age')::float8 * interval '1 second' "
            "AND (:'qid' = '' OR question_id = :'qid') RETURNING " + _PUBLIC_COLUMNS + ") "
            "SELECT coalesce(json_agg(r), '[]'::json) FROM r;",
            by=FALLBACK_ACCEPTED_BY, eid=DESK_EXPERT_ID, origin=self._text(origin, "origin", required=False),
            age=str(float(min_age_seconds)), qid=question_id,
        )
        for row in rows:
            self._changed("question", row["question_id"])
        return rows

    def reopen(self, question_id: str) -> None:
        """Hands a question the fallback claimed but could not start back to `open`."""
        self._json(
            "WITH r AS (UPDATE expert_questions SET status = 'open', accepted_by = NULL WHERE question_id = :'qid' "
            "AND status = 'accepted' AND accepted_by = :'by' RETURNING 1) SELECT coalesce(json_agg(r), '[]'::json) FROM r;",
            qid=self._text(question_id, "question_id"), by=FALLBACK_ACCEPTED_BY,
        )
        self._changed("question", question_id)

    def mark_announced(self, question_id: str, kind: str) -> None:
        column = {"answer": "answer_notified_at", "question": "expert_notified_at"}.get(kind)
        if column is None:
            raise ExpertRegistryError("kind must be 'answer' or 'question'.")
        self._json(
            f"WITH r AS (UPDATE expert_questions SET {column} = now() WHERE question_id = :'qid' RETURNING 1) "
            "SELECT coalesce(json_agg(r), '[]'::json) FROM r;",
            qid=self._text(question_id, "question_id"),
        )


_registry: ExpertRegistry | None = None
_registry_lock = threading.Lock()


def get_registry() -> ExpertRegistry:
    """The process-wide registry (the default Desk-wide cluster)."""
    global _registry
    with _registry_lock:
        if _registry is None:
            _registry = ExpertRegistry()
        return _registry


def set_registry(registry: ExpertRegistry | None) -> None:
    """Replaces the process-wide registry (tests)."""
    global _registry
    with _registry_lock:
        _registry = registry
