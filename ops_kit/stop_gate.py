"""Stop hook: hold the turn open while the scope checklist has unresolved items.

Input  (stdin):  the Stop hook JSON from Claude Code. Fields used here:
                 session_id, cwd, hook_event_name, stop_hook_active, background_tasks.
Output (stdout): nothing to allow the stop, or one JSON object:
                 {"decision": "block", "reason": "..."}  keeps Claude working
                 {"systemMessage": "..."}                allows, with a note for the user
Exit code is always 0. The hook fails open: bad input or an internal error
never traps a session.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import IO, List, Mapping, Optional

from . import checklist as cl

MAX_LISTED = 10
ALLOW = "allow"
BLOCK = "block"


@dataclass
class Decision:
    action: str
    reason: str = ""
    system_message: str = ""

    def to_output(self) -> Optional[dict]:
        if self.action == BLOCK:
            return {"decision": "block", "reason": self.reason}
        if self.system_message:
            return {"systemMessage": self.system_message}
        return None


def _missing_scope_reason(payload: Mapping, env: Mapping[str, str]) -> str:
    name = cl.scope_file_name(payload.get("session_id"))
    return (
        "ops-kit: this session has no scope checklist. Write %s/%s with one "
        "'- [ ] item (done when: <check>)' line per task, then tick each item with evidence "
        "or label it 'blocked: <reason>' or 'open: <next step and owner>'."
        % (cl.scope_dir_name(env), name)
    )


def _block_reason(path_text: str, items: List[cl.Item], require_evidence: bool) -> str:
    lines = [
        "ops-kit: %d scope item(s) in %s are unresolved, so the turn cannot end yet."
        % (len(items), path_text)
    ]
    for item in items[:MAX_LISTED]:
        kind = "ticked without evidence" if item.checked else "unticked, no label"
        text = item.text if len(item.text) <= 160 else item.text[:157] + "..."
        lines.append("  line %d (%s): %s" % (item.line_no, kind, text))
    if len(items) > MAX_LISTED:
        lines.append("  ... and %d more" % (len(items) - MAX_LISTED))
    lines.append("Give every listed item one of three end states in the scope file:")
    lines.append("  done: finish it, verify it, tick it '- [x]' and add 'evidence: <check output or id>'")
    lines.append("  blocked: keep '- [ ]' and add 'blocked: <first failing check and what the user must do>'")
    lines.append("  open: keep '- [ ]' and add 'open: <next step and who owns it>'")
    if require_evidence:
        lines.append("Strict mode is on: a ticked item without 'evidence:' counts as unresolved.")
    return "\n".join(lines)


def evaluate(payload: Mapping, env: Mapping[str, str]) -> Decision:
    """Pure decision function. Reads the scope file, touches nothing else."""
    if cl.env_flag(env, "OPS_KIT_DISABLE"):
        return Decision(ALLOW)
    if payload.get("hook_event_name") not in (None, "Stop"):
        return Decision(ALLOW)

    stop_hook_active = payload.get("stop_hook_active") is True
    if stop_hook_active and cl.env_flag(env, "OPS_KIT_BLOCK_ONCE"):
        return Decision(ALLOW)

    session_id = payload.get("session_id")
    cwd = payload.get("cwd")
    if not cl.short_session_id(session_id) or not isinstance(cwd, str) or not cwd.strip():
        return Decision(ALLOW)

    require_scope = cl.env_flag(env, "OPS_KIT_REQUIRE_SCOPE")
    require_evidence = cl.env_flag(env, "OPS_KIT_REQUIRE_EVIDENCE")

    path = cl.find_scope_file(cwd, session_id, env)
    items = cl.read_scope(path) if path else []
    if not items:
        # A missing checklist can only be asked for once per stop sequence,
        # otherwise a pure question-and-answer session would loop.
        if require_scope and not stop_hook_active:
            return Decision(BLOCK, reason=_missing_scope_reason(payload, env))
        return Decision(ALLOW)

    pending = cl.unresolved(items, require_evidence)
    path_text = cl.display_path(path, cwd)
    if not pending:
        tally = cl.counts(items, require_evidence)
        carried = tally[cl.BLOCKED] + tally[cl.OPEN]
        if carried:
            return Decision(
                ALLOW,
                system_message="ops-kit: scope has %d blocked and %d open item(s) carried forward (%s)."
                % (tally[cl.BLOCKED], tally[cl.OPEN], path_text),
            )
        return Decision(ALLOW)

    background = payload.get("background_tasks")
    if (
        isinstance(background, list)
        and background
        and cl.env_flag(env, "OPS_KIT_ALLOW_WHEN_BACKGROUND", default=True)
    ):
        return Decision(
            ALLOW,
            system_message="ops-kit: %d scope item(s) still unresolved in %s. Not blocking because "
            "%d background task(s) are running, so the session is paused, not done."
            % (len(pending), path_text, len(background)),
        )

    return Decision(BLOCK, reason=_block_reason(path_text, pending, require_evidence))


def main(stdin: IO[str], stdout: IO[str], stderr: IO[str], env: Mapping[str, str]) -> int:
    try:
        payload = json.loads(stdin.read() or "{}")
        if not isinstance(payload, dict):
            raise ValueError("hook input is not a JSON object")
        output = evaluate(payload, env).to_output()
    except Exception as exc:  # fail open, never trap a session on a hook bug
        stderr.write("ops-kit stop gate skipped: %s\n" % exc)
        return 0
    if output is not None:
        stdout.write(json.dumps(output))
        stdout.write("\n")
    return 0


if __name__ == "__main__":
    import os

    sys.exit(main(sys.stdin, sys.stdout, sys.stderr, os.environ))
