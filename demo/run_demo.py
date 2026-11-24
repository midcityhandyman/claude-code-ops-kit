"""Offline simulator: replay a session's hook events through the real hook scripts.

No Claude Code, network or keys needed. It builds a throwaway working directory,
pipes sample hook JSON into scripts/session_start.py and scripts/stop_gate.py the
way Claude Code does, edits the scope file between stops, then runs the wrap-up.

Run:  python demo/run_demo.py            (prints the walkthrough)
      python demo/run_demo.py --save     (also writes demo/output.txt)
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
SESSION = "d3m05e55-0000-4000-8000-00000000abcd"
SCOPE_NAME = "scope-d3m05e55.md"

SCOPE_V1 = """# Scope: weekly report export

- [ ] Add CSV export to the weekly report (done when: pytest tests/test_export.py passes)
- [ ] Update the README usage section (done when: grep -c "export" README.md is above 0)
- [ ] Email the sample file to Alex Sample at alex@example.com (done when: outbox shows the message)
"""

SCOPE_V2 = """# Scope: weekly report export

- [x] Add CSV export to the weekly report (done when: pytest tests/test_export.py passes) evidence: 6 passed in 0.41s
- [x] Update the README usage section (done when: grep -c "export" README.md is above 0) evidence: grep count is 3
- [ ] Email the sample file to Alex Sample at alex@example.com (done when: outbox shows the message)
      blocked: no mail tool in this session. The user must send demo/sample.csv by hand.
- [ ] Add an XLSX export. open: next step is choosing a writer library, owner is the user
"""

NOTES = """Added CSV export to the weekly report and documented it. Goal met except the email.
Changed report/export.py, tests/test_export.py and README.md.
Chose the standard csv module over a dataframe library to keep installs at zero.
Next session: the XLSX export is still open and needs a library decision first.
"""

LINES = []


def say(text=""):
    LINES.append(text)
    print(text)


def run(script, args=(), payload=None, cwd=None):
    stdin = json.dumps(payload).encode("utf-8") if payload is not None else b""
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args], input=stdin, capture_output=True, cwd=str(cwd), timeout=60
    )
    return result.returncode, result.stdout.decode("utf-8").strip(), result.stderr.decode("utf-8").strip()


def stop_payload(cwd, active):
    return {
        "session_id": SESSION,
        "transcript_path": "~/.claude/projects/demo/%s.jsonl" % SESSION,
        "cwd": str(cwd),
        "permission_mode": "default",
        "hook_event_name": "Stop",
        "stop_hook_active": active,
        "last_assistant_message": "The export works. STATUS: done",
        "background_tasks": [],
        "session_crons": [],
    }


def show_stop(step, cwd, active):
    code, out, _ = run("stop_gate.py", payload=stop_payload(cwd, active), cwd=cwd)
    say("%s Stop hook fires (stop_hook_active=%s)" % (step, str(active).lower()))
    say("    exit code: %d" % code)
    if not out:
        say("    stdout: (empty)  ->  turn ends")
        return
    output = json.loads(out)
    if output.get("decision") == "block":
        say('    stdout: {"decision": "block", "reason": ...}  ->  Claude keeps working. Reason:')
        for line in output["reason"].splitlines():
            say("      | " + line)
    else:
        say("    stdout: %s  ->  turn ends" % json.dumps(output))


def main():
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        scope = cwd / ".context" / SCOPE_NAME

        say("ops-kit demo: one session, replayed offline through the real hook scripts")
        say("=" * 74)
        say()
        say("[1] SessionStart hook fires")
        payload = {"session_id": SESSION, "cwd": str(cwd), "hook_event_name": "SessionStart", "source": "startup"}
        _, out, _ = run("session_start.py", payload=payload, cwd=cwd)
        for line in json.loads(out)["hookSpecificOutput"]["additionalContext"].splitlines():
            say("      | " + line)
        say()

        show_stop("[2]", cwd, False)
        say("    (no scope file yet, so there is nothing to enforce)")
        say()

        scope.parent.mkdir()
        scope.write_text(SCOPE_V1, encoding="utf-8")
        say("[3] Claude writes .context/%s with 3 items, does some of the work, tries to stop" % SCOPE_NAME)
        show_stop("   ", cwd, False)
        say()

        scope.write_text(SCOPE_V2, encoding="utf-8")
        say("[4] Claude ticks 2 items with evidence, labels 1 blocked, adds 1 open, tries again")
        _, out, _ = run("scope_status.py", ["--session", SESSION], cwd=cwd)
        for line in out.splitlines():
            say("      | " + line)
        show_stop("   ", cwd, True)
        say()

        say("[5] Wrap-up skill runs write_summary.py --strict")
        notes = cwd / "notes.txt"
        notes.write_text(NOTES, encoding="utf-8")
        args = ["--session", SESSION, "--title", "Weekly report CSV export", "--notes-file", str(notes)]
        args += ["--strict", "--now", "2030-01-15T17:30:00+00:00"]
        code, out, err = run("write_summary.py", args, cwd=cwd)
        say("    exit code: %d" % code)
        for line in (out or err).splitlines():
            say("      | " + line)
        say()
        say("--- .context/session-summaries/2030-01-15-d3m05e55.md ---")
        say((cwd / ".context" / "session-summaries" / "2030-01-15-d3m05e55.md").read_text(encoding="utf-8").rstrip())
        say()
        say("--- .context/session-log.jsonl ---")
        say((cwd / ".context" / "session-log.jsonl").read_text(encoding="utf-8").rstrip())

    if "--save" in sys.argv[1:]:
        (REPO / "demo" / "output.txt").write_text("\n".join(LINES) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    main()
