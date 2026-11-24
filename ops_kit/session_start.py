"""SessionStart hook: tell Claude where this session's scope checklist lives.

Output (stdout) is the documented SessionStart shape:
    {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "..."}}
"""

from __future__ import annotations

import json
import sys
from typing import IO, Mapping, Optional

from . import checklist as cl


def build_context(payload: Mapping, env: Mapping[str, str]) -> Optional[str]:
    if cl.env_flag(env, "OPS_KIT_DISABLE"):
        return None
    session_id = payload.get("session_id")
    name = cl.scope_file_name(session_id)
    if not name:
        return None
    rel = "%s/%s" % (cl.scope_dir_name(env), name)
    lines = [
        "ops-kit scope checklist for this session: %s (relative to the working directory)." % rel,
        "For any task that changes files or runs commands, write the scope there first, "
        "one line per item: '- [ ] item (done when: <check>)'.",
        "The check is a command, query or read-back that fails now and passes when the item is done.",
        "End every item in one of three states: '- [x] ... evidence: <proof>', "
        "'- [ ] ... blocked: <first failing check and what the user must do>', "
        "or '- [ ] ... open: <next step and who owns it>'.",
        "A Stop hook holds the turn open while any unticked item has no blocked: or open: label.",
    ]
    cwd = payload.get("cwd")
    path = cl.find_scope_file(cwd, session_id, env) if isinstance(cwd, str) else None
    if path:
        tally = cl.counts(cl.read_scope(path))
        lines.append(
            "The file already exists: %d done, %d blocked, %d open, %d unlabeled."
            % (tally[cl.DONE], tally[cl.BLOCKED], tally[cl.OPEN], tally[cl.UNLABELED])
        )
    return "\n".join(lines)


def main(stdin: IO[str], stdout: IO[str], stderr: IO[str], env: Mapping[str, str]) -> int:
    try:
        payload = json.loads(stdin.read() or "{}")
        if not isinstance(payload, dict):
            raise ValueError("hook input is not a JSON object")
        context = build_context(payload, env)
    except Exception as exc:  # fail open
        stderr.write("ops-kit session start skipped: %s\n" % exc)
        return 0
    if context:
        output = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}
        stdout.write(json.dumps(output))
        stdout.write("\n")
    return 0


if __name__ == "__main__":
    import os

    sys.exit(main(sys.stdin, sys.stdout, sys.stderr, os.environ))
