"""TODO c2555b5: the expert registry (real throwaway PostgreSQL cluster) + the desk_*_expert MCP tools."""
import asyncio
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from desk import expert_registry as er  # noqa: E402
from desk import temp_ui  # noqa: E402

passed = failed = 0


def check(name, ok):
    global passed, failed
    if ok:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


def raises(fn, text=""):
    try:
        fn()
    except er.ExpertRegistryError as e:
        return text in str(e)
    return False


# ---- no PostgreSQL: one clear error, no crash ----
_real_find = er.find_pg_bin
er.find_pg_bin = lambda: None
try:
    check("without PostgreSQL every call reports one clear error", raises(lambda: er.ExpertRegistry(Path("/nonexistent/pgdata")).list_experts(), "PostgreSQL was not found"))
finally:
    er.find_pg_bin = _real_find

if er.find_pg_bin() is None:
    print("SKIP: no PostgreSQL installation found; the live registry checks were not run")
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)

# A unix socket path is limited to ~100 characters, which $TMPDIR's long macOS path would exceed.
root = Path(tempfile.mkdtemp(prefix="pgx", dir="/tmp"))
reg = er.ExpertRegistry(root / "pgdata")
try:
    changes = []
    reg.add_listener(lambda kind, ident: changes.append((kind, ident)))

    experts = reg.list_experts()
    check("first use provisions the cluster; the built-in user expert exists",
          reg.cluster_exists() and sorted(e["expert_id"] for e in experts) == ["desk", "user"] and [e for e in experts if e["expert_id"] == "user"][0]["kind"] == "human")
    reg.ensure()
    check("ensure is idempotent", len(reg.list_experts()) == 2)

    # experts
    e = reg.register_expert("docs-bot", "Docs bot", "answers doc questions", "agent", "me")
    check("register returns the expert", e["expert_id"] == "docs-bot" and e["registered_by"] == "me")
    check("update by the same registrant works", reg.register_expert("docs-bot", "Docs bot 2", "", "agent", "me")["name"] == "Docs bot 2")
    check("update by someone else is refused", raises(lambda: reg.register_expert("docs-bot", "x", "", "agent", "other"), "someone else"))
    check("the built-in user expert cannot be changed", raises(lambda: reg.register_expert("user", "x", "", "human", "desk"), "cannot be changed"))
    check("bad expert ids are refused", raises(lambda: reg.register_expert("Bad Id", "x"), "expert_id"))
    check("bad kinds are refused", raises(lambda: reg.register_expert("k1", "x", "", "wizard"), "kind"))
    check("registering notified listeners", ("expert", "docs-bot") in changes)

    # questions
    nasty = "What's \"this\"?\n; DROP TABLE experts; -- \\ back\\slash"
    note = "if yes update section 3'; DELETE FROM expert_questions; --"
    q = reg.ask("docs-bot", nasty, "tester", note)
    qid = q["question_id"]
    check("ask returns an open question without the note", q["status"] == "open" and "note_to_self" not in q and q["question"] == nasty)
    check("a hostile question and note are stored literally, tables intact",
          reg.get_question(qid)["question"] == nasty and len(reg.list_experts()) == 3)
    check("the expert-side read never includes the note", all("note_to_self" not in x for x in reg.list_questions("docs-bot")))
    check("the asker's read includes the note", reg.get_question(qid, include_note=True)["note_to_self"] == note)
    check("asking an unknown expert lists the registered ones", raises(lambda: reg.ask("nope", "q"), "docs-bot"))
    check("empty question refused", raises(lambda: reg.ask("docs-bot", "  "), "question"))

    check("list by status", len(reg.list_questions("docs-bot", ["open"])) == 1 and reg.list_questions("docs-bot", ["answered"]) == [])
    check("bad status refused", raises(lambda: reg.list_questions("docs-bot", ["nope"]), "status"))
    check("accept moves open -> accepted", reg.accept(qid, "worker")["status"] == "accepted")
    check("accepting twice is refused", raises(lambda: reg.accept(qid, "w2"), "accepted"))
    check("a poller sees nothing to announce yet", reg.claim_announcements("/d/a") == [])
    a = reg.answer(qid, "Yes, 42.", "worker")
    check("answer records text, who and when", a["status"] == "answered" and a["answer"] == "Yes, 42." and a["answered_by"] == "worker" and a["answered_at"])
    check("answering twice is refused", raises(lambda: reg.answer(qid, "again"), "answered"))
    check("an unknown question id is reported", raises(lambda: reg.answer("nope", "x"), "No question"))

    got = reg.claim_announcements("/d/a")
    check("the answered question is claimed (an origin-less one goes to any Desk)",
          [(x["kind"], x["question"]["question_id"]) for x in got] == [("answer", qid)] and "note_to_self" not in got[0]["question"])
    check("a claim stamps it, so the next claim is empty", reg.claim_announcements("/d/a") == [] and reg.claim_announcements("/d/b") == [])
    check("bad announce kind refused", raises(lambda: reg.mark_announced(qid, "x"), "kind"))

    uq = reg.ask("user", "Which database?", "agent")
    check("a question for user is claimed once",
          [(x["kind"], x["question"]["question_id"]) for x in reg.claim_announcements("/d/a")] == [("question", uq["question_id"])]
          and reg.claim_announcements("/d/a") == [])
    mk = reg.ask("user", "Another?", "agent")
    reg.mark_announced(mk["question_id"], "question")
    check("mark_announced still suppresses a banner", reg.claim_announcements("/d/a") == [])
    reg.withdraw(mk["question_id"])

    # -- the built-in desk expert's fallback (TODO 86a837e) --
    d1 = reg.ask("desk", "how does X work?", "agent", origin="/d/a")
    d2 = reg.ask("desk", "origin-less", "agent")
    d3 = reg.ask("desk", "from B", "agent", origin="/d/b")
    check("nothing is claimed before the wait is over", reg.claim_fallback("/d/a") == [])
    got = reg.claim_fallback("/d/a", min_age_seconds=0)
    check("a Desk claims its own and origin-less questions, not another Desk's",
          sorted(x["question_id"] for x in got) == sorted([d1["question_id"], d2["question_id"]])
          and all(x["status"] == "accepted" and x["accepted_by"] == "desk-fallback" for x in got))
    check("a claim is not repeated", reg.claim_fallback("/d/a", min_age_seconds=0) == [])
    check("the other Desk still gets its own", [x["question_id"] for x in reg.claim_fallback("/d/b", min_age_seconds=0)] == [d3["question_id"]])
    d4 = reg.ask("desk", "someone is on it", "agent", origin="/d/a")
    reg.accept(d4["question_id"], "human")
    check("an already-accepted question is left alone", reg.claim_fallback("/d/a", min_age_seconds=0) == [])
    d5 = reg.ask("desk", "by id", "agent", origin="/d/a")
    d6 = reg.ask("desk", "other", "agent", origin="/d/a")
    check("a claim can be limited to one question",
          [x["question_id"] for x in reg.claim_fallback("/d/a", d5["question_id"], 0)] == [d5["question_id"]]
          and reg.get_question(d6["question_id"])["status"] == "open")
    reg.reopen(d5["question_id"])
    check("reopen hands a claimed question back", reg.get_question(d5["question_id"])["status"] == "open")
    reg.reopen(d4["question_id"])
    check("reopen leaves someone else's acceptance alone", reg.get_question(d4["question_id"])["accepted_by"] == "human")
    q_other = reg.ask("docs-bot", "not for desk", "agent", origin="/d/a")
    check("only the desk expert is claimed", q_other["question_id"] not in [x["question_id"] for x in reg.claim_fallback("/d/a", min_age_seconds=0)])

    # -- several Desks (TODO 488cf49) --
    reg.register_expert("multi-bot", "Multi", "x", "agent", "t")
    qa = reg.ask("multi-bot", "from A", "agent", origin="/d/a")
    qb = reg.ask("multi-bot", "from B", "agent", origin="/d/b")
    reg.heartbeat("/d/a"); reg.heartbeat("/d/b")
    reg.answer(qa["question_id"], "ra", "t"); reg.answer(qb["question_id"], "rb", "t")
    ids = lambda items: sorted(x["question"]["question_id"] for x in items)
    check("Desk A is told only about its own answer while B is running", ids(reg.claim_announcements("/d/a")) == [qa["question_id"]])
    check("Desk B then gets its own", ids(reg.claim_announcements("/d/b")) == [qb["question_id"]])
    qc = reg.ask("multi-bot", "from A again", "agent", origin="/d/a")
    reg.answer(qc["question_id"], "rc", "t")
    check("a different Desk does not take A's answer while A is running", reg.claim_announcements("/d/b") == [])
    check("A still gets it", ids(reg.claim_announcements("/d/a")) == [qc["question_id"]])
    qd = reg.ask("multi-bot", "from a closed Desk", "agent", origin="/d/gone")
    reg.answer(qd["question_id"], "rd", "t")
    check("an answer for a Desk that never checked in goes to whichever Desk claims it", ids(reg.claim_announcements("/d/b")) == [qd["question_id"]])
    qe = reg.ask("multi-bot", "from a Desk that stopped", "agent", origin="/d/old")
    reg.heartbeat("/d/old")
    reg._exec("UPDATE desk_presence SET seen_at = now() - interval '5 minutes' WHERE origin = '/d/old';")
    reg.answer(qe["question_id"], "re", "t")
    check("a Desk that stopped checking in no longer holds its answers", ids(reg.claim_announcements("/d/a")) == [qe["question_id"]])
    qf = reg.ask("multi-bot", "race", "agent", origin="")
    reg.answer(qf["question_id"], "rf", "t")
    import concurrent.futures as cf
    with cf.ThreadPoolExecutor(6) as pool:
        results = list(pool.map(lambda i: reg.claim_announcements(f"/d/{i}"), range(6)))
    check("six Desks claiming at once: exactly one gets it", sum(len(r) for r in results) == 1)
    check("withdraw works while open", reg.withdraw(uq["question_id"])["status"] == "withdrawn")
    reg.mark_handed_off(qid)
    check("handoff is stamped", reg.get_question(qid)["handed_off_at"] is not None)
    check("listeners saw question changes", ("question", qid) in changes)

    # -- reports to listening experts (TODO 0f506f7) --
    check("the desk expert listens by default, user does not",
          [e["expert_id"] for e in reg.listening_experts()] == ["desk"])
    check("a report to a non-listening expert is refused, naming who listens",
          raises(lambda: reg.report("docs-bot", "t", "f"), "not listening") and raises(lambda: reg.report("docs-bot", "t", "f"), "desk ("))
    check("reporting to an unknown expert is refused", raises(lambda: reg.report("nope", "t", "f"), "No expert"))
    lst = reg.register_expert("lib-expert", "Lib", "knows libs", "agent", "t", listens_for="Pitfalls of library X")
    check("registering with listens_for makes an expert listen", lst["listens_for"] == "Pitfalls of library X"
          and "lib-expert" in [e["expert_id"] for e in reg.listening_experts()])
    check("empty title or finding refused", raises(lambda: reg.report("lib-expert", " ", "f"), "title")
          and raises(lambda: reg.report("lib-expert", "t", ""), "finding"))
    rep = reg.report("lib-expert", "X leaks handles", "X leaks a handle per call", "ran: lsof | wc -l", "agent", "/d/a")
    check("a report starts new and carries what was given",
          rep["status"] == "new" and rep["title"] == "X leaks handles" and rep["evidence"] == "ran: lsof | wc -l" and rep["reporter"] == "agent")
    hostile = "'; DROP TABLE expert_reports; -- \\ :'x' \n\"q\""
    h = reg.report("lib-expert", hostile, hostile, hostile)
    check("hostile text is stored literally", reg.get_report(h["report_id"])["finding"] == hostile)
    check("list defaults and filters", len(reg.list_reports("lib-expert", ["new"])) == 2 and reg.list_reports("lib-expert", ["integrated"]) == []
          and raises(lambda: reg.list_reports("lib-expert", ["x"]), "status"))
    check("bad decision refused", raises(lambda: reg.review_report(rep["report_id"], "maybe"), "decision"))
    check("rejecting needs a note", raises(lambda: reg.review_report(rep["report_id"], "rejected"), "note"))
    r1 = reg.review_report(rep["report_id"], "accepted", "", "lib-agent")
    check("accepting records who and when", r1["status"] == "accepted" and r1["reviewed_by"] == "lib-agent" and r1["reviewed_at"])
    r2 = reg.integrate_report(rep["report_id"], "Added to docs/pitfalls.md", "lib-agent")
    check("integrating records the note", r2["status"] == "integrated" and r2["integration_note"] == "Added to docs/pitfalls.md" and r2["integrated_at"])
    check("an integrated report cannot be reviewed again", raises(lambda: reg.review_report(rep["report_id"], "rejected", "n"), "integrated"))
    check("integration needs a note", raises(lambda: reg.integrate_report(h["report_id"], " "), "integration_note"))
    d = reg.review_report(h["report_id"], "duplicate", "same as the pitfalls doc")
    check("duplicate keeps the reason", d["status"] == "duplicate" and d["review_note"] == "same as the pitfalls doc")
    check("an unknown report id is reported", raises(lambda: reg.review_report("nope", "accepted"), "No report"))
    check("listeners saw report changes", ("report", rep["report_id"]) in changes)

    # the cluster going away is recovered from
    reg.stop()
    check("a stopped cluster is brought back on the next call", reg.get_question(qid)["status"] == "answered")

    # MCP tools
    from desk.shell import desk_mcp_server as mcp  # noqa: E402

    er.set_registry(reg)

    def call(tool, args):
        res = asyncio.run(tool.handler(args))
        return res, res["content"][0]["text"]

    names = {"desk_list_experts", "desk_register_expert", "desk_ask_expert", "desk_get_expert_question",
             "desk_list_expert_questions", "desk_accept_expert_question", "desk_answer_expert_question"}
    check("all seven tools are registered", names <= {t.name for t in mcp._TOOLS})
    check("the five report tools are registered", {"desk_report_to_expert", "desk_get_expert_report", "desk_list_expert_reports",
          "desk_review_expert_report", "desk_integrate_expert_report"} <= {t.name for t in mcp._TOOLS})
    res, text = call(mcp._list_experts, {})
    check("list tool returns JSON", not res["is_error"] and {x["expert_id"] for x in json.loads(text)} >= {"user", "docs-bot"})
    res, text = call(mcp._register_expert, {"expert_id": "mcp-bot", "name": "MCP bot", "registered_by": "t"})
    check("register tool works", not res["is_error"] and json.loads(text)["expert_id"] == "mcp-bot")
    res, text = call(mcp._ask_expert, {"expert_id": "mcp-bot", "question": "ping?", "note_to_self": "secret"})
    mq = json.loads(text)["question_id"]
    check("ask tool returns a question id and not the note", not res["is_error"] and "secret" not in text)
    res, text = call(mcp._get_expert_question, {"question_id": mq})
    check("asker's get includes the private note", json.loads(text)["note_to_self"] == "secret")
    res, text = call(mcp._list_expert_questions, {"expert_id": "mcp-bot"})
    check("expert-side list is open-only and note-free", [x["question_id"] for x in json.loads(text)] == [mq] and "secret" not in text)
    res, text = call(mcp._accept_expert_question, {"question_id": mq, "accepted_by": "bot"})
    check("accept tool works", json.loads(text)["status"] == "accepted")
    res, text = call(mcp._register_expert, {"expert_id": "mcp-ears", "name": "Ears", "registered_by": "t", "listens_for": "anything about ears"})
    check("register tool takes listens_for", not res["is_error"] and json.loads(text)["listens_for"] == "anything about ears")
    res, text = call(mcp._report_to_expert, {"expert_id": "mcp-bot", "title": "t", "finding": "f"})
    check("reporting to a non-listener is a tool error", res["is_error"] and "not listening" in text)
    res, text = call(mcp._report_to_expert, {"expert_id": "mcp-ears", "title": "Ears ring", "finding": "they do", "evidence": "e"})
    rid = json.loads(text)["report_id"]
    check("report tool returns a report id", not res["is_error"] and json.loads(text)["status"] == "new")
    res, text = call(mcp._list_expert_reports, {"expert_id": "mcp-ears"})
    check("expert-side report list defaults to pending", [x["report_id"] for x in json.loads(text)] == [rid])
    res, text = call(mcp._review_expert_report, {"report_id": rid, "decision": "accepted"})
    check("review tool works", json.loads(text)["status"] == "accepted")
    res, text = call(mcp._list_expert_reports, {"expert_id": "mcp-ears"})
    check("accepted is still pending", len(json.loads(text)) == 1)
    res, text = call(mcp._integrate_expert_report, {"report_id": rid, "integration_note": "in ears.md"})
    check("integrate tool works", json.loads(text)["status"] == "integrated")
    res, text = call(mcp._get_expert_report, {"report_id": rid})
    check("reporter's get shows the outcome", json.loads(text)["integration_note"] == "in ears.md")
    res, text = call(mcp._list_expert_reports, {"expert_id": "mcp-ears"})
    check("integrated leaves the pending list", json.loads(text) == [])
    res, text = call(mcp._get_expert_report, {"report_id": "nope"})
    check("unknown report is a tool error", res["is_error"])
    res, text = call(mcp._answer_expert_question, {"question_id": mq, "answer": "pong", "answered_by": "bot"})
    check("answer tool works", json.loads(text)["answer"] == "pong")
    res, text = call(mcp._list_expert_questions, {"expert_id": "mcp-bot", "status": "all"})
    check("status all lists answered ones too", len(json.loads(text)) == 1)
    res, text = call(mcp._answer_expert_question, {"question_id": mq, "answer": "again"})
    check("a registry error is a tool error", res["is_error"] is True and "answered" in text)
    res, text = call(mcp._ask_expert, {"expert_id": "ghost", "question": "x"})
    check("asking an unknown expert is a tool error", res["is_error"] is True)
    er.set_registry(None)
finally:
    reg.stop()
    shutil.rmtree(root, ignore_errors=True)

tag = "desk_*_expert MCP tools + expert registry #434481"
check("changelog tag current, with an entry", tag in temp_ui.CURRENT_TAGS and tag in temp_ui._NEW_FEATURES)
check("report tag current, with an entry", "desk_report_to_expert: findings to experts #532898" in temp_ui.CURRENT_TAGS and "desk_report_to_expert: findings to experts #532898" in temp_ui._NEW_FEATURES)
doc = temp_ui.SPLIT_DOC_CONTENT["tempui-experts.md"]
check("dedicated doc names every tool", all(n in doc for n in (
    "desk_list_experts", "desk_register_expert", "desk_ask_expert", "desk_get_expert_question",
    "desk_list_expert_questions", "desk_accept_expert_question", "desk_answer_expert_question",
    "desk_report_to_expert", "desk_get_expert_report", "desk_list_expert_reports", "desk_review_expert_report",
    "desk_integrate_expert_report")))

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
