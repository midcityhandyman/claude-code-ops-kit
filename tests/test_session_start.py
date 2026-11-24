import io
import json

from conftest import SHORT, load_hook_json
from ops_kit import session_start


def run_main(payload, env=None):
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    out, err = io.StringIO(), io.StringIO()
    code = session_start.main(io.StringIO(raw), out, err, env or {})
    text = out.getvalue().strip()
    return code, (json.loads(text) if text else None)


def test_emits_documented_output_shape(workdir):
    code, output = run_main(load_hook_json("session_start.json", workdir))
    assert code == 0
    specific = output["hookSpecificOutput"]
    assert specific["hookEventName"] == "SessionStart"
    assert ".context/scope-%s.md" % SHORT in specific["additionalContext"]
    assert "done when:" in specific["additionalContext"]
    assert "already exists" not in specific["additionalContext"]


def test_reports_existing_file_on_resume(workdir, write_scope):
    write_scope("- [x] a\n- [ ] b\n- [ ] c. open: later, owner is the user\n")
    payload = load_hook_json("session_start.json", workdir)
    payload["source"] = "resume"
    context = run_main(payload)[1]["hookSpecificOutput"]["additionalContext"]
    assert "1 done, 0 blocked, 1 open, 1 unlabeled" in context


def test_custom_dir_and_disable(workdir):
    payload = load_hook_json("session_start.json", workdir)
    context = run_main(payload, {"OPS_KIT_SCOPE_DIR": "notes"})[1]["hookSpecificOutput"]["additionalContext"]
    assert "notes/scope-%s.md" % SHORT in context
    assert run_main(payload, {"OPS_KIT_DISABLE": "1"})[1] is None


def test_fails_open():
    assert run_main("not json") == (0, None)
    assert run_main({"hook_event_name": "SessionStart"}) == (0, None)
