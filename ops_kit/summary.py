"""Wrap-up: write a session summary from the scope checklist plus free-form notes.

Writes two things under <cwd>/<scope dir>/:
    session-summaries/<date>-<short id>.md   the readable summary
    session-log.jsonl                        one JSON line per wrap-up, for feeds and reports

Exit codes: 0 written, 1 refused (strict mode and items are still unlabeled), 2 bad usage.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, List, Mapping, Optional, Sequence

from . import checklist as cl

SUMMARY_DIR = "session-summaries"
LOG_FILE = "session-log.jsonl"


def _section(title: str, items: Sequence[cl.Item]) -> List[str]:
    if not items:
        return []
    return ["## %s (%d)" % (title, len(items)), ""] + ["- %s" % item.text for item in items] + [""]


def build_summary(
    items: Sequence[cl.Item], session_id: str, title: str, notes: str, now: datetime, scope_file: str
) -> str:
    short = cl.short_session_id(session_id)
    tally = cl.counts(items)
    by_state = {state: [i for i in items if i.state() == state] for state in tally}
    lines = [
        "# Session %s: %s" % (short, title or "wrap-up"),
        "",
        "- Session: %s" % short,
        "- Written: %s" % now.strftime("%Y-%m-%d %H:%M %Z").strip(),
        "- Scope file: %s" % (scope_file or "none"),
        "- Items: %d done, %d blocked, %d open, %d unlabeled"
        % (tally[cl.DONE], tally[cl.BLOCKED], tally[cl.OPEN], tally[cl.UNLABELED]),
        "",
    ]
    if notes.strip():
        lines += ["## Summary", "", notes.strip(), ""]
    lines += _section("Done", by_state[cl.DONE])
    lines += _section("Blocked", by_state[cl.BLOCKED])
    lines += _section("Open", by_state[cl.OPEN])
    lines += _section("Unlabeled, needs an end state", by_state[cl.UNLABELED])
    if not items:
        lines += ["No scope checklist items were recorded for this session.", ""]
    return "\n".join(lines).rstrip() + "\n"


def write_summary(
    cwd: str, session_id: str, title: str, notes: str, now: datetime, env: Mapping[str, str], strict: bool = False
) -> dict:
    """Write the summary and log line. Returns a result dict with 'written' true or false."""
    short = cl.short_session_id(session_id)
    if not short:
        raise ValueError("session id is empty or has no usable characters")
    scope_path = cl.find_scope_file(cwd, session_id, env)
    items = cl.read_scope(scope_path) if scope_path else []
    tally = cl.counts(items)
    if strict and tally[cl.UNLABELED]:
        return {"written": False, "unlabeled": [i.text for i in cl.unresolved(items)], "counts": tally}

    base = Path(cwd) / cl.scope_dir_name(env)
    out_dir = base / SUMMARY_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / ("%s-%s.md" % (now.strftime("%Y-%m-%d"), short))
    scope_text = cl.display_path(scope_path, cwd) if scope_path else ""
    out_path.write_text(build_summary(items, session_id, title, notes, now, scope_text), encoding="utf-8")

    record = {
        "session": short,
        "written_at": now.isoformat(timespec="seconds"),
        "title": title,
        "summary": "session %s: %s" % (short, (notes.strip().splitlines() or [title or "wrap-up"])[0]),
        "counts": {k: tally[k] for k in (cl.DONE, cl.BLOCKED, cl.OPEN, cl.UNLABELED)},
        "summary_file": cl.display_path(out_path, cwd),
    }
    with (base / LOG_FILE).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
    return {"written": True, "path": cl.display_path(out_path, cwd), "record": record, "counts": tally}


def _parse_now(value: Optional[str]) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def main(argv: Sequence[str], stdin: IO[str], stdout: IO[str], stderr: IO[str], env: Mapping[str, str]) -> int:
    parser = argparse.ArgumentParser(prog="write_summary", description="Write a session wrap-up summary.")
    parser.add_argument("--session", required=True, help="session id (the first 8 characters are used)")
    parser.add_argument("--cwd", default=".", help="session working directory (default: current directory)")
    parser.add_argument("--title", default="", help="one-line title for the session")
    parser.add_argument("--notes", default="", help="summary text, or '-' to read it from stdin")
    parser.add_argument("--notes-file", default="", help="read the summary text from this file")
    parser.add_argument("--now", default="", help="ISO timestamp to use instead of the clock (for tests)")
    parser.add_argument("--strict", action="store_true", help="refuse while any item is unticked and unlabeled")
    try:
        args = parser.parse_args(list(argv))
    except SystemExit:
        return 2

    notes = args.notes
    if args.notes_file:
        notes = Path(args.notes_file).read_text(encoding="utf-8")
    elif notes == "-":
        notes = stdin.read()
    try:
        result = write_summary(args.cwd, args.session, args.title, notes, _parse_now(args.now), env, args.strict)
    except (ValueError, OSError) as exc:
        stderr.write("ops-kit wrap-up failed: %s\n" % exc)
        return 2

    if not result["written"]:
        stderr.write("ops-kit wrap-up refused: %d item(s) have no end state:\n" % len(result["unlabeled"]))
        for text in result["unlabeled"]:
            stderr.write("  - %s\n" % text)
        stderr.write("Tick them with evidence, or label them blocked: or open:, then run wrap-up again.\n")
        return 1
    tally = result["counts"]
    stdout.write("wrote %s\n" % result["path"])
    stdout.write(
        "items: %d done, %d blocked, %d open, %d unlabeled\n"
        % (tally[cl.DONE], tally[cl.BLOCKED], tally[cl.OPEN], tally[cl.UNLABELED])
    )
    return 0


if __name__ == "__main__":
    import os

    sys.exit(main(sys.argv[1:], sys.stdin, sys.stdout, sys.stderr, os.environ))
