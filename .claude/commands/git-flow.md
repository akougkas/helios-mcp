---
allowed-tools: Bash(git *)
description: Create feature branch and manage git workflow
argument-hint: feature|fix|refactor [branch-name]
---

## Git Feature Branch

### Create and switch to feature branch
!`git checkout -b $1/$2`

### Verify branch
!`git branch --show-current`

**Branch created:** Now work on `$1/$2` branch. 
Remember: Small, atomic commits throughout the session.