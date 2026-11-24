---
name: wrapup
description: Close out the session by writing a session summary from the scope checklist. Use when the user says they are finishing, wrapping up or closing out, or when the session's work is done and it ran commands or changed files. Skip for short question-and-answer sessions.
argument-hint: "[optional one-line title]"
---

# Wrap up the session

This session's id is `${CLAUDE_SESSION_ID}`. Title, if one was passed: $ARGUMENTS

## Steps

1. Open the scope file, `.context/scope-<first 8 characters of the session id>.md`.
   Every item must be in an end state before you summarize: ticked with evidence,
   `blocked:` with the one thing the user must do, or `open:` with the next step and
   owner. Finish or label anything that is not.
2. Write the summary notes, 3 to 8 plain lines, first line first:
   - line 1: what the session was for and whether it got there
   - what changed (files, records, deploys), with ids where they exist
   - decisions made and why
   - anything the next session needs to know before it starts
   Do not include secrets, tokens or personal details of third parties.
3. Save the notes to a temporary file, then run:

   ```
   python "${CLAUDE_PLUGIN_ROOT}/scripts/write_summary.py" --session ${CLAUDE_SESSION_ID} --title "<one-line title>" --notes-file <path to notes> --strict
   ```

   `--strict` makes the script refuse (exit code 1) while any item is unticked and
   unlabeled. If it refuses, go back to step 1. Do not drop `--strict` to get past it.
4. Read back the file the script printed and confirm it matches the session.
5. Tell the user, in one or two lines: the summary path, the item counts, and each
   blocked item with the one thing they must do.

## What gets written

- `.context/session-summaries/<date>-<short id>.md`: the readable summary.
- `.context/session-log.jsonl`: one JSON line per wrap-up. Its `summary` field starts
  with `session <short id>` so downstream feeds can label the entry.

If the script fails for any other reason, say so in one line and give the user the
summary text directly instead.
