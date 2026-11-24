---
name: scope
description: Write or update this session's scope checklist. Use at the start of any task that changes files or runs commands, when the user adds or drops work mid-task, or when the Stop hook reports unresolved scope items.
argument-hint: "[task description]"
---

# Session scope checklist

The scope file for this session is `.context/scope-<first 8 characters of the session id>.md`
in the working directory. This session's id is `${CLAUDE_SESSION_ID}`. If the
`OPS_KIT_SCOPE_DIR` setting is in use, replace `.context` with that folder.

Task, if one was passed: $ARGUMENTS

## Write the scope

1. Create the folder if it is missing, then create the file. Never write to a shared
   `scope.md`: several sessions can share one working directory.
2. Add one line per deliverable, in this exact shape:

   ```
   - [ ] <item> (done when: <check>)
   ```

   The check is a command, a query or a read-back that fails right now and will pass
   when the item is done. "Looks right" is not a check.
3. Keep items small enough that each has one check. Split anything with "and" in it.

## Close every item

Each item ends in exactly one of three states. Edit the line in place.

| State | Line shape | What the note must say |
| :- | :- | :- |
| done | `- [x] <item> evidence: <proof>` | The check output, a record id, or a timestamp. Verify by a different route than the one that made the change. |
| blocked | `- [ ] <item> blocked: <reason>` | The first failing check, plus the one thing the user must do. |
| open | `- [ ] <item> open: <next step>` | The next step and who owns it. |

Fix in-scope problems as you find them and add a line for each. Do not end a turn by
reporting an in-scope problem and asking whether to fix it.

## Check the file

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/scope_status.py" --session ${CLAUDE_SESSION_ID}
```

It prints each item with its state and exits 1 while anything is unlabeled, which is
exactly the condition the Stop hook refuses.
