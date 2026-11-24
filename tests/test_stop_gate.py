import io
import json
import subprocess
import sys

from conftest import REPO, SHORT, load_hook_json
from ops_kit import stop_gate

MIXED = (REPO / "tests" / "fixtures" / "scope_mixed.md").read_text(encoding="utf-8")
RESOLVED = (
    "- [x] Add retry. evidence: 14 passed\n"
    "- [ ] Rotate the staging token. blocked: needs an admin to approve it\n"
    "- [ ] Backfill old rows. open: dry run next, owner is the data team\n"
)


def run_main(payload, env=None):
    """Feed hook JSON through main() the way Claude Code does, return (code, stdout json, stderr)."""
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    out, err = io.StringIO(), io.StringIO()
    code = stop_gate.main(io.StringIO(raw), out, err, env or {})
    text = out.getvalue().strip()
    return code, (json.loads(text) if text else None), err.getvalue()


def test_no_scope_file_allows_silently(workdir):
    assert run_main(load_hook_json("stop_basic.json", workdir)) == (0, None, "")


def test_unlabeled_items_block_with_documented_shape(workdir, write_scope):
    write_scope(MIXED)
    code, output, _ = run_main(load_hook_json("stop_basic.json", workdir))
    assert code == 0
    assert set(output) == {"decision", "reason"}
    assert output["decision"] == "block"
    reason = output["reason"]
    assert "2 scope item(s)" in reason
    assert ".context/scope-%s.md" % SHORT in reason
    assert "line 4" in reason and "Update the runbook" in reason
    assert "line 13" in reason
    assert "Rotate the staging token" not in reason  # labelled blocked, so not listed
    assert "blocked:" in reason and "open:" in reason  # tells Claude how to resolve


def test_all_items_in_end_states_allows_with_note(workdir, write_scope):
    write_scope(RESOLVED)
    code, output, _ = run_main(load_hook_json("stop_basic.json", workdir))
    assert code == 0
    assert "decision" not in output
    assert "1 blocked and 1 open" in output["systemMessage"]


def test_all_ticked_allows_silently(workdir, write_scope):
    write_scope("- [x] one\n- [x] two\n")
    assert run_main(load_hook_json("stop_basic.json", workdir)) == (0, None, "")


def test_empty_scope_file_allows(workdir, write_scope):
    write_scope("# Scope\n\nnothing yet\n")
    assert run_main(load_hook_json("stop_basic.json", workdir))[1] is None


def test_still_blocks_when_stop_hook_active_by_default(workdir, write_scope):
    write_scope("- [ ] unfinished\n")
    payload = load_hook_json("stop_basic.json", workdir)
    payload["stop_hook_active"] = True
    assert run_main(payload)[1]["decision"] == "block"


def test_block_once_allows_when_stop_hook_active(workdir, write_scope):
    write_scope("- [ ] unfinished\n")
    payload = load_hook_json("stop_basic.json", workdir)
    assert run_main(payload, {"OPS_KIT_BLOCK_ONCE": "1"})[1]["decision"] == "block"
    payload["stop_hook_active"] = True
    assert run_main(payload, {"OPS_KIT_BLOCK_ONCE": "1"})[1] is None


def test_background_tasks_pause_instead_of_block(workdir, write_scope):
    write_scope("- [ ] unfinished\n")
    payload = load_hook_json("stop_active_with_background.json", workdir)
    _, output, _ = run_main(payload)
    assert "decision" not in output
    assert "1 background task(s)" in output["systemMessage"]
    _, strict, _ = run_main(payload, {"OPS_KIT_ALLOW_WHEN_BACKGROUND": "0"})
    assert strict["decision"] == "block"


def test_require_evidence_blocks_bare_ticks(workdir, write_scope):
    write_scope("- [x] bare tick\n")
    payload = load_hook_json("stop_basic.json", workdir)
    assert run_main(payload)[1] is None
    output = run_main(payload, {"OPS_KIT_REQUIRE_EVIDENCE": "1"})[1]
    assert output["decision"] == "block"
    assert "ticked without evidence" in output["reason"]


def test_require_scope_blocks_once_when_file_missing(workdir):
    payload = load_hook_json("stop_basic.json", workdir)
    output = run_main(payload, {"OPS_KIT_REQUIRE_SCOPE": "1"})[1]
    assert output["decision"] == "block"
    assert "scope-%s.md" % SHORT in output["reason"]
    payload["stop_hook_active"] = True
    assert run_main(payload, {"OPS_KIT_REQUIRE_SCOPE": "1"})[1] is None


def test_custom_scope_dir(workdir, write_scope):
    write_scope("- [ ] unfinished\n", folder="notes")
    payload = load_hook_json("stop_basic.json", workdir)
    assert run_main(payload)[1] is None
    output = run_main(payload, {"OPS_KIT_SCOPE_DIR": "notes"})[1]
    assert "notes/scope-%s.md" % SHORT in output["reason"]


def test_other_sessions_scope_file_is_ignored(workdir):
    (workdir / ".context" / "scope-0therses.md").write_text("- [ ] not mine\n", encoding="utf-8")
    assert run_main(load_hook_json("stop_basic.json", workdir))[1] is None


def test_disable_flag(workdir, write_scope):
    write_scope("- [ ] unfinished\n")
    assert run_main(load_hook_json("stop_basic.json", workdir), {"OPS_KIT_DISABLE": "1"})[1] is None


def test_other_hook_events_are_ignored(workdir, write_scope):
    write_scope("- [ ] unfinished\n")
    payload = load_hook_json("stop_basic.json", workdir)
    payload["hook_event_name"] = "SubagentStop"
    assert run_main(payload)[1] is None


def test_long_lists_are_truncated(workdir, write_scope):
    write_scope("".join("- [ ] item %d\n" % n for n in range(25)))
    reason = run_main(load_hook_json("stop_basic.json", workdir))[1]["reason"]
    assert "25 scope item(s)" in reason and "... and 15 more" in reason
    assert "item 9" in reason and "item 10\n" not in reason


def test_fails_open_on_bad_input():
    for raw in ("not json", "[1, 2]", ""):
        code, output, err = run_main(raw)
        assert code == 0 and output is None
    assert "skipped" in run_main("not json")[2]


def test_missing_fields_allow():
    assert run_main({"hook_event_name": "Stop"})[1] is None
    assert run_main({"hook_event_name": "Stop", "session_id": "abc", "cwd": 7})[1] is None


def test_entry_script_end_to_end(workdir, write_scope):
    """Run the real script the hook config points at, with JSON on stdin."""
    write_scope("- [ ] Send the note to Alex Sample (done when: outbox shows it)\n")
    payload = json.dumps(load_hook_json("stop_basic.json", workdir))
    script = str(REPO / "scripts" / "stop_gate.py")
    result = subprocess.run(
        [sys.executable, script], input=payload.encode("utf-8"), capture_output=True, cwd=str(workdir), timeout=60
    )
    assert result.returncode == 0
    output = json.loads(result.stdout.decode("utf-8"))
    assert output["decision"] == "block" and "Alex Sample" in output["reason"]
