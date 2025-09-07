---
allowed-tools: Bash(git status), Bash(git branch), Bash(git log), Bash(git stash), Read
description: Initialize session from clean git state
argument-hint: [task-description]
---

## Quick Session Start

### Git State
Branch: !`git branch --show-current`  
Status: !`git status -s`  
Last commit: !`git log --oneline -1`

### Check for uncommitted work
!`if [ -n "$(git status --porcelain)" ]; then echo "⚠️ UNCOMMITTED CHANGES DETECTED - stash or commit first"; fi`

### Load Context
@CLAUDE.md (skim for key rules)

### Session Task
$ARGUMENTS

### Ready
If git is clean, proceed. If not, handle uncommitted work first.