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
          reg.cluster_exists() and [e["expert_id"] for e in experts] == ["user"] and experts[0]["kind"] == "human")
    reg.ensure()
    check("ensure is idempotent", len(reg.list_experts()) == 1)

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
          reg.get_question(qid)["question"] == nasty and len(reg.list_experts()) == 2)
    check("the expert-side read never includes the note", all("note_to_self" not in x for x in reg.list_questions("docs-bot")))
    check("the asker's read includes the note", reg.get_question(qid, include_note=True)["note_to_self"] == note)
    check("asking an unknown expert lists the registered ones", raises(lambda: reg.ask("nope", "q"), "docs-bot"))
    check("empty question refused", raises(lambda: reg.ask("docs-bot", "  "), "question"))

    check("list by status", len(reg.list_questions("docs-bot", ["open"])) == 1 and reg.list_questions("docs-bot", ["answered"]) == [])
    check("bad status refused", raises(lambda: reg.list_questions("docs-bot", ["nope"]), "status"))
    check("accept moves open -> accepted", reg.accept(qid, "worker")["status"] == "accepted")
    check("accepting twice is refused", raises(lambda: reg.accept(qid, "w2"), "accepted"))
    check("a poller sees nothing to announce yet", reg.unannounced_answers() == [])
    a = reg.answer(qid, "Yes, 42.", "worker")
    check("answer records text, who and when", a["status"] == "answered" and a["answer"] == "Yes, 42." and a["answered_by"] == "worker" and a["answered_at"])
    check("answering twice is refused", raises(lambda: reg.answer(qid, "again"), "answered"))
    check("an unknown question id is reported", raises(lambda: reg.answer("nope", "x"), "No question"))

    check("the answered question awaits announcement", [x["question_id"] for x in reg.unannounced_answers()] == [qid])
    reg.mark_announced(qid, "answer")
    check("marking it announced clears it", reg.unannounced_answers() == [])
    check("bad announce kind refused", raises(lambda: reg.mark_announced(qid, "x"), "kind"))

    uq = reg.ask("user", "Which database?", "agent")
    check("a question for user awaits announcement", [x["question_id"] for x in reg.unannounced_questions_for_user()] == [uq["question_id"]])
    reg.mark_announced(uq["question_id"], "question")
    check("announced questions are not repeated", reg.unannounced_questions_for_user() == [])
    check("withdraw works while open", reg.withdraw(uq["question_id"])["status"] == "withdrawn")
    reg.mark_handed_off(qid)
    check("handoff is stamped", reg.get_question(qid)["handed_off_at"] is not None)
    check("listeners saw question changes", ("question", qid) in changes)

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
doc = temp_ui.SPLIT_DOC_CONTENT["tempui-experts.md"]
check("dedicated doc names every tool", all(n in doc for n in (
    "desk_list_experts", "desk_register_expert", "desk_ask_expert", "desk_get_expert_question",
    "desk_list_expert_questions", "desk_accept_expert_question", "desk_answer_expert_question")))

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
