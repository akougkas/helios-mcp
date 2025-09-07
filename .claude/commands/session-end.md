---
allowed-tools: Bash(git status), Bash(git add), Bash(git commit), Bash(git diff), Bash(find), Bash(rm), Write, Append
description: Clean, commit, and prepare handoff
argument-hint: [what-was-accomplished]
---

## Session End Protocol

### 1. Clean Temporary Files
!`find . -type f \( -name "*.tmp" -o -name "*.debug" -o -name "*.log" -o -name ".DS_Store" \) -not -path "./.git/*" -delete 2>/dev/null`
!`find . -type d -name "__pycache__" -not -path "./.git/*" -exec rm -rf {} + 2>/dev/null`

### 2. Review Changes
Status: !`git status -s`
Diff summary: !`git diff --stat HEAD`

### 3. Stage and Commit
!`git add -A`
!`git status -s`

Create atomic commit:
!`git commit -m "$ARGUMENTS

Session handoff: Repository in clean, working state"`

### 4. Update DEVLOG
Append to DEVLOG.md:
```
## $(date +%Y-%m-%d_%H:%M)
**Done:** $ARGUMENTS
**Next:** [Check git log for context]
---
```

### 5. Verify Clean State
!`git status`

**Handoff ready:** Next session starts from clean commit.