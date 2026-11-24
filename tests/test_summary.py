import io
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

from conftest import REPO, SESSION, SHORT
from ops_kit import summary

MIXED = (REPO / "tests" / "fixtures" / "scope_mixed.md").read_text(encoding="utf-8")
RESOLVED = (
    "- [x] Add retry. evidence: 14 passed\n"
    "- [ ] Rotate the staging token. blocked: needs an admin to approve it\n"
    "- [ ] Backfill old rows. open: dry run next, owner is the data team\n"
)
NOW = datetime(2030, 1, 15, 17, 30, tzinfo=timezone.utc)


def run_cli(args, stdin=""):
    out, err = io.StringIO(), io.StringIO()
    code = summary.main(args, io.StringIO(stdin), out, err, {})
    return code, out.getvalue(), err.getvalue()


def test_writes_summary_and_log_line(workdir, write_scope):
    write_scope(RESOLVED)
    result = summary.write_summary(str(workdir), SESSION, "Sync hardening", "Added retry.\nSecond line.", NOW, {})
    assert result["written"] and result["path"] == ".context/session-summaries/2030-01-15-%s.md" % SHORT
    text = (workdir / ".context" / "session-summaries" / ("2030-01-15-%s.md" % SHORT)).read_text(encoding="utf-8")
    assert text.startswith("# Session %s: Sync hardening\n" % SHORT)
    assert "- Items: 1 done, 1 blocked, 1 open, 0 unlabeled" in text
    assert "## Blocked (1)" in text and "blocked: needs an admin to approve it" in text
    assert "## Open (1)" in text and "## Done (1)" in text
    assert "Unlabeled" not in text
    lines = (workdir / ".context" / "session-log.jsonl").read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[0])
    assert record["summary"] == "session %s: Added retry." % SHORT
    assert record["counts"] == {"done": 1, "blocked": 1, "open": 1, "unlabeled": 0}
    assert record["written_at"] == "2030-01-15T17:30:00+00:00"


def test_log_appends_one_line_per_wrapup(workdir, write_scope):
    write_scope(RESOLVED)
    for _ in range(2):
        summary.write_summary(str(workdir), SESSION, "t", "n", NOW, {})
    assert len((workdir / ".context" / "session-log.jsonl").read_text(encoding="utf-8").splitlines()) == 2


def test_strict_refuses_and_writes_nothing(workdir, write_scope):
    write_scope(MIXED)
    code, out, err = run_cli(["--session", SESSION, "--cwd", str(workdir), "--strict", "--notes", "x"])
    assert code == 1 and out == ""
    assert "2 item(s) have no end state" in err and "Update the runbook" in err
    assert not (workdir / ".context" / "session-summaries").exists()
    assert not (workdir / ".context" / "session-log.jsonl").exists()


def test_non_strict_lists_unlabeled_items(workdir, write_scope):
    write_scope(MIXED)
    code, out, _ = run_cli(
        ["--session", SESSION, "--cwd", str(workdir), "--notes", "x", "--now", "2030-01-15T17:30:00+00:00"]
    )
    assert code == 0 and "2 unlabeled" in out
    text = (workdir / ".context" / "session-summaries" / ("2030-01-15-%s.md" % SHORT)).read_text(encoding="utf-8")
    assert "## Unlabeled, needs an end state (2)" in text


def test_notes_from_stdin_and_file(workdir, tmp_path):
    base = ["--session", SESSION, "--cwd", str(workdir), "--now", "2030-01-15T17:30:00"]
    assert run_cli(base + ["--notes", "-"], stdin="From stdin.\n")[0] == 0
    notes = tmp_path / "notes.txt"
    notes.write_text("From a file.\n", encoding="utf-8")
    assert run_cli(base + ["--notes-file", str(notes)])[0] == 0
    records = [
        json.loads(line)
        for line in (workdir / ".context" / "session-log.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [r["summary"] for r in records] == ["session %s: From stdin." % SHORT, "session %s: From a file." % SHORT]


def test_session_without_scope_file_still_summarizes(workdir):
    code, out, _ = run_cli(["--session", SESSION, "--cwd", str(workdir), "--notes", "Quick fix.", "--strict"])
    assert code == 0 and "0 done" in out
    files = list((workdir / ".context" / "session-summaries").iterdir())
    assert "No scope checklist items were recorded" in files[0].read_text(encoding="utf-8")


def test_bad_usage(workdir):
    assert run_cli(["--cwd", str(workdir)])[0] == 2
    code, _, err = run_cli(["--session", "///", "--cwd", str(workdir)])
    assert code == 2 and "session id" in err


def test_missing_notes_file_is_a_clean_error(workdir):
    code, out, err = run_cli(["--session", SESSION, "--cwd", str(workdir), "--notes-file", str(workdir / "nope.txt")])
    assert code == 2 and out == "" and "wrap-up failed" in err
    assert not (workdir / ".context" / "session-log.jsonl").exists()


def test_strict_honors_require_evidence_like_the_stop_hook(workdir, write_scope):
    write_scope("- [x] Add retry\n- [ ] Backfill. open: dry run next, owner is the data team\n")
    args = (str(workdir), SESSION, "t", "n", NOW)
    refused = summary.write_summary(*args, {"OPS_KIT_REQUIRE_EVIDENCE": "1"}, strict=True)
    assert refused["written"] is False and refused["unlabeled"] == ["Add retry"]
    assert summary.write_summary(*args, {}, strict=True)["written"] is True


def test_scope_status_exit_code_matches_the_stop_hook(workdir, write_scope):
    write_scope("- [x] Add retry\n- [ ] Backfill. open: dry run next, owner is the data team\n")
    script = str(REPO / "scripts" / "scope_status.py")

    def status(strict):
        env = {k: v for k, v in os.environ.items() if not k.startswith("OPS_KIT_")}
        env["OPS_KIT_REQUIRE_EVIDENCE"] = strict
        result = subprocess.run(
            [sys.executable, script, "--session", SESSION, "--cwd", str(workdir)],
            capture_output=True,
            env=env,
            timeout=60,
        )
        return result.returncode, result.stdout.decode("utf-8")

    assert status("0")[0] == 0
    code, out = status("1")
    assert code == 1 and out.startswith("unproven") and "1 ticked without evidence" in out
