---
allowed-tools: Bash(git add), Bash(git commit), Bash(git status)
description: Quick atomic commit during work
argument-hint: [commit-message]
---

## Quick Commit

!`git add -A && git commit -m "$ARGUMENTS" && git status -s`

**Committed:** Work saved with message "$ARGUMENTS"