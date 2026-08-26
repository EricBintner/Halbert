# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Git Documentation Scraper.

Phase 27: RAG Coverage

Comprehensive Git guides covering:
- Basic commands
- Branching and merging
- Remote operations
- Git configuration
- Advanced workflows
"""

import logging
from typing import List
from datetime import datetime
from pathlib import Path

from .base import BaseScraper, ScrapedDocument, ScraperConfig

logger = logging.getLogger('halbert')


class GitDocsScraper(BaseScraper):
    """Generates comprehensive Git documentation."""
    
    def __init__(self, config: ScraperConfig):
        super().__init__(config)
    
    def get_source_name(self) -> str:
        return "git-docs"
    
    def scrape(self) -> List[ScrapedDocument]:
        """Generate Git documentation."""
        logger.info("Generating Git documentation...")
        
        documents = []
        documents.extend(self._generate_guides())
        
        logger.info(f"Total Git documents: {len(documents)}")
        return documents
    
    def _generate_guides(self) -> List[ScrapedDocument]:
        """Generate all Git guides."""
        guides = []
        
        guides.append(self._basics_guide())
        guides.append(self._branching_guide())
        guides.append(self._remote_guide())
        guides.append(self._config_guide())
        guides.append(self._stash_guide())
        guides.append(self._rebase_guide())
        guides.append(self._troubleshooting_guide())
        guides.append(self._workflows_guide())
        
        return guides
    
    def _basics_guide(self) -> ScrapedDocument:
        """Git basics guide."""
        content = """# Git Basics Guide

## Setup

```bash
# Configure user
git config --global user.name "Your Name"
git config --global user.email "you@example.com"

# Configure editor
git config --global core.editor vim

# View config
git config --list
git config user.name
```

## Initialize Repository

```bash
# New repository
git init
git init project-name

# Clone existing
git clone https://github.com/user/repo.git
git clone git@github.com:user/repo.git
git clone repo.git local-name
git clone --depth 1 repo.git          # Shallow clone
```

## Basic Workflow

```bash
# Check status
git status
git status -s                          # Short format

# Stage changes
git add file.txt
git add .                              # All changes
git add -A                             # All (including deletions)
git add -p                             # Interactive staging

# Commit
git commit -m "Message"
git commit -am "Message"               # Add + commit tracked
git commit --amend                     # Modify last commit
git commit --amend --no-edit           # Keep message

# View log
git log
git log --oneline
git log --graph --oneline --all
git log -n 5                           # Last 5
git log --author="name"
git log --since="2024-01-01"
git log -p file.txt                    # With patches
```

## View Changes

```bash
# Unstaged changes
git diff
git diff file.txt

# Staged changes
git diff --staged
git diff --cached

# Between commits
git diff commit1 commit2
git diff HEAD~3 HEAD

# Show commit
git show commit_hash
git show HEAD
```

## Undo Changes

```bash
# Unstage file
git reset file.txt
git restore --staged file.txt

# Discard changes
git checkout -- file.txt
git restore file.txt

# Reset to commit
git reset --soft HEAD~1               # Keep changes staged
git reset --mixed HEAD~1              # Keep changes unstaged
git reset --hard HEAD~1               # Discard changes

# Revert commit (creates new commit)
git revert commit_hash
```

## File Operations

```bash
# Remove file
git rm file.txt
git rm --cached file.txt              # Keep in working dir

# Move/rename file
git mv old.txt new.txt

# Ignore files
echo "*.log" >> .gitignore
```

## History

```bash
# Blame (who changed what)
git blame file.txt

# Search commits
git log --grep="keyword"
git log -S"code"                      # Search code changes

# Find deleted file
git log --all --full-history -- path/to/file
```
"""
        return ScrapedDocument(
            id=self._generate_id("git-basics"),
            url="https://git-scm.com/docs",
            title="Git Basics Guide",
            content=content,
            source=self.get_source_name(),
            category="development",
            tags=["git", "version-control", "basics"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _branching_guide(self) -> ScrapedDocument:
        """Git branching guide."""
        content = """# Git Branching Guide

## Branch Operations

```bash
# List branches
git branch                             # Local
git branch -r                          # Remote
git branch -a                          # All

# Create branch
git branch branch-name
git branch branch-name commit          # From specific commit

# Switch branch
git checkout branch-name
git switch branch-name                 # Git 2.23+

# Create and switch
git checkout -b branch-name
git switch -c branch-name

# Rename branch
git branch -m old-name new-name
git branch -m new-name                 # Current branch

# Delete branch
git branch -d branch-name              # Safe delete
git branch -D branch-name              # Force delete
```

## Merging

```bash
# Merge branch into current
git merge branch-name

# Merge with commit message
git merge branch-name -m "Merge branch"

# Merge without fast-forward
git merge --no-ff branch-name

# Abort merge
git merge --abort

# Continue after resolving conflicts
git add .
git commit
```

## Merge Conflicts

```bash
# View conflicts
git status
git diff --name-only --diff-filter=U

# Conflict markers in file:
<<<<<<< HEAD
Current changes
=======
Incoming changes
>>>>>>> branch-name

# After resolving
git add resolved-file.txt
git commit

# Use theirs/ours
git checkout --theirs file.txt
git checkout --ours file.txt
```

## Cherry-pick

```bash
# Apply specific commit
git cherry-pick commit_hash

# Without committing
git cherry-pick -n commit_hash

# Continue after conflict
git cherry-pick --continue

# Abort
git cherry-pick --abort
```

## Tracking Branches

```bash
# Set upstream
git branch --set-upstream-to=origin/main
git push -u origin branch-name

# View tracking
git branch -vv

# Create tracking branch
git checkout --track origin/branch
git checkout -b local origin/remote
```

## Branch Comparison

```bash
# Commits in A not in B
git log B..A

# Commits in either but not both
git log A...B

# List branches containing commit
git branch --contains commit_hash

# List branches merged into current
git branch --merged
git branch --no-merged
```
"""
        return ScrapedDocument(
            id=self._generate_id("git-branching"),
            url="https://git-scm.com/book/en/v2/Git-Branching-Branches-in-a-Nutshell",
            title="Git Branching Guide",
            content=content,
            source=self.get_source_name(),
            category="development",
            tags=["git", "branching", "merging"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _remote_guide(self) -> ScrapedDocument:
        """Git remote operations guide."""
        content = """# Git Remote Operations Guide

## Remote Management

```bash
# List remotes
git remote
git remote -v                          # With URLs

# Add remote
git remote add origin https://github.com/user/repo.git
git remote add upstream https://github.com/original/repo.git

# Remove remote
git remote remove origin

# Rename remote
git remote rename old new

# Change URL
git remote set-url origin new-url

# Show remote info
git remote show origin
```

## Fetch and Pull

```bash
# Fetch updates
git fetch
git fetch origin
git fetch --all                        # All remotes
git fetch --prune                      # Remove deleted refs

# Pull (fetch + merge)
git pull
git pull origin main
git pull --rebase                      # Rebase instead of merge
git pull --ff-only                     # Only fast-forward
```

## Push

```bash
# Push to remote
git push
git push origin main
git push -u origin main                # Set upstream

# Push all branches
git push --all

# Push tags
git push --tags
git push origin tag-name

# Force push (careful!)
git push --force
git push --force-with-lease            # Safer force push

# Delete remote branch
git push origin --delete branch-name
git push origin :branch-name
```

## Tags

```bash
# List tags
git tag
git tag -l "v1.*"

# Create tag
git tag v1.0.0
git tag -a v1.0.0 -m "Version 1.0.0"   # Annotated
git tag v1.0.0 commit_hash             # On specific commit

# Show tag
git show v1.0.0

# Push tags
git push origin v1.0.0
git push origin --tags

# Delete tag
git tag -d v1.0.0
git push origin --delete v1.0.0
```

## Submodules

```bash
# Add submodule
git submodule add https://github.com/user/repo.git path/to/sub

# Clone with submodules
git clone --recursive repo.git
git clone --recurse-submodules repo.git

# Initialize submodules (after clone)
git submodule init
git submodule update
git submodule update --init --recursive

# Update submodules
git submodule update --remote

# Remove submodule
git submodule deinit path/to/sub
git rm path/to/sub
rm -rf .git/modules/path/to/sub
```

## Fork Workflow

```bash
# Setup
git clone https://github.com/you/forked-repo.git
git remote add upstream https://github.com/original/repo.git

# Sync fork with upstream
git fetch upstream
git checkout main
git merge upstream/main
git push origin main

# Or rebase
git rebase upstream/main
git push --force-with-lease origin main
```
"""
        return ScrapedDocument(
            id=self._generate_id("git-remote"),
            url="https://git-scm.com/book/en/v2/Git-Basics-Working-with-Remotes",
            title="Git Remote Operations Guide",
            content=content,
            source=self.get_source_name(),
            category="development",
            tags=["git", "remote", "push", "pull"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _config_guide(self) -> ScrapedDocument:
        """Git configuration guide."""
        content = """# Git Configuration Guide

## Configuration Levels

```bash
# System (all users)
git config --system setting value
# File: /etc/gitconfig

# Global (current user)
git config --global setting value
# File: ~/.gitconfig

# Local (repository)
git config --local setting value
# File: .git/config

# View all settings
git config --list
git config --list --show-origin
```

## Essential Settings

```bash
# Identity
git config --global user.name "Your Name"
git config --global user.email "you@example.com"

# Editor
git config --global core.editor "vim"
git config --global core.editor "code --wait"

# Default branch
git config --global init.defaultBranch main

# Auto-correct
git config --global help.autocorrect 1

# Credential caching
git config --global credential.helper cache
git config --global credential.helper 'cache --timeout=3600'
git config --global credential.helper store          # Store permanently
```

## Aliases

```bash
# Create alias
git config --global alias.co checkout
git config --global alias.br branch
git config --global alias.ci commit
git config --global alias.st status

# Useful aliases
git config --global alias.lg "log --graph --oneline --all"
git config --global alias.last "log -1 HEAD"
git config --global alias.unstage "reset HEAD --"
git config --global alias.visual "!gitk"
```

## Line Endings

```bash
# Auto-convert line endings
git config --global core.autocrlf input      # Linux/Mac
git config --global core.autocrlf true       # Windows

# Prevent commits with mixed endings
git config --global core.safecrlf true
```

## Diff and Merge Tools

```bash
# Set diff tool
git config --global diff.tool vimdiff
git config --global diff.tool vscode
git config --global difftool.vscode.cmd 'code --wait --diff $LOCAL $REMOTE'

# Set merge tool
git config --global merge.tool vimdiff
git config --global merge.tool vscode
git config --global mergetool.vscode.cmd 'code --wait $MERGED'

# Use tool
git difftool
git mergetool
```

## .gitignore

```gitignore
# Comments
# Ignore file
file.txt

# Ignore pattern
*.log
*.tmp

# Ignore directory
/build/
node_modules/

# Negate (don't ignore)
!important.log

# Ignore everywhere
**/temp/

# Ignore in root only
/config.local
```

```bash
# Global gitignore
git config --global core.excludesfile ~/.gitignore_global

# Check what's ignoring a file
git check-ignore -v file.txt
```

## Example ~/.gitconfig

```ini
[user]
    name = Your Name
    email = you@example.com

[core]
    editor = vim
    autocrlf = input
    pager = less -FRX

[init]
    defaultBranch = main

[alias]
    co = checkout
    br = branch
    ci = commit
    st = status
    lg = log --graph --oneline --decorate --all

[pull]
    rebase = true

[push]
    default = current
    autoSetupRemote = true

[diff]
    colorMoved = zebra

[merge]
    conflictstyle = diff3
```
"""
        return ScrapedDocument(
            id=self._generate_id("git-config"),
            url="https://git-scm.com/book/en/v2/Customizing-Git-Git-Configuration",
            title="Git Configuration Guide",
            content=content,
            source=self.get_source_name(),
            category="development",
            tags=["git", "configuration", "gitconfig"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "medium"}
        )
    
    def _stash_guide(self) -> ScrapedDocument:
        """Git stash guide."""
        content = """# Git Stash Guide

## Basic Stash Operations

```bash
# Stash changes
git stash
git stash push
git stash push -m "Description"

# Include untracked files
git stash -u
git stash --include-untracked

# Include all files (even ignored)
git stash -a
git stash --all

# Stash specific files
git stash push -m "message" file1.txt file2.txt
git stash push -p                      # Interactive
```

## View Stashes

```bash
# List stashes
git stash list

# Show stash contents
git stash show
git stash show -p                      # With diff
git stash show stash@{2}               # Specific stash
```

## Apply Stashes

```bash
# Apply most recent (keep in list)
git stash apply

# Apply specific stash
git stash apply stash@{2}

# Apply and remove from list
git stash pop
git stash pop stash@{2}

# Apply to different branch
git checkout other-branch
git stash apply
```

## Delete Stashes

```bash
# Delete specific stash
git stash drop stash@{2}

# Delete most recent
git stash drop

# Delete all stashes
git stash clear
```

## Advanced Operations

```bash
# Create branch from stash
git stash branch new-branch
git stash branch new-branch stash@{2}

# Stash only staged changes
git stash push --staged

# Stash with keeping staged
git stash push --keep-index

# Show stash diff
git diff stash@{0}
git diff stash@{0} file.txt
```

## Common Workflows

### Interrupt Current Work
```bash
# Working on feature, need to fix bug
git stash push -m "WIP: feature-x"
git checkout main
# Fix bug, commit
git checkout feature-branch
git stash pop
```

### Move Changes to New Branch
```bash
# Made changes on wrong branch
git stash
git checkout -b correct-branch
git stash pop
```

### Partially Apply Stash
```bash
# View stash files
git stash show --name-only stash@{0}

# Apply specific file
git checkout stash@{0} -- path/to/file
```
"""
        return ScrapedDocument(
            id=self._generate_id("git-stash"),
            url="https://git-scm.com/docs/git-stash",
            title="Git Stash Guide",
            content=content,
            source=self.get_source_name(),
            category="development",
            tags=["git", "stash", "workflow"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "medium"}
        )
    
    def _rebase_guide(self) -> ScrapedDocument:
        """Git rebase guide."""
        content = """# Git Rebase Guide

## Basic Rebase

```bash
# Rebase current branch onto main
git checkout feature
git rebase main

# Or from feature branch
git rebase main feature

# Abort rebase
git rebase --abort

# Continue after resolving conflicts
git add .
git rebase --continue

# Skip problematic commit
git rebase --skip
```

## Interactive Rebase

```bash
# Rebase last N commits
git rebase -i HEAD~3

# Rebase from specific commit
git rebase -i commit_hash

# Rebase onto different base
git rebase -i --onto newbase oldbase
```

### Interactive Commands

```
pick   - use commit as-is
reword - use commit but edit message
edit   - use commit but stop for amending
squash - merge into previous commit
fixup  - like squash but discard message
drop   - remove commit
```

### Example: Squash Commits
```bash
git rebase -i HEAD~3

# Editor opens:
pick abc123 First commit
squash def456 Second commit
squash ghi789 Third commit

# Save, then edit combined message
```

### Example: Reorder Commits
```bash
git rebase -i HEAD~3

# Change order in editor:
pick ghi789 Third commit
pick abc123 First commit
pick def456 Second commit
```

### Example: Edit Commit
```bash
git rebase -i HEAD~3

# Mark commit as 'edit':
edit abc123 Commit to change
pick def456 Other commit

# Make changes
git add .
git commit --amend
git rebase --continue
```

## Rebase vs Merge

### Merge
```bash
# Creates merge commit
git checkout feature
git merge main
```

### Rebase
```bash
# Replays commits on top
git checkout feature
git rebase main
```

### When to Use What

**Rebase:**
- Clean up local commits before push
- Keep feature branch up to date
- Squash WIP commits

**Merge:**
- Public/shared branches
- Preserve complete history
- Team collaboration

## Golden Rules

1. **Never rebase public/shared branches**
2. **Only rebase local, unpushed commits**
3. **If already pushed, use merge instead**

## Recovering from Bad Rebase

```bash
# Find original HEAD
git reflog

# Reset to before rebase
git reset --hard HEAD@{N}

# Or reset to original branch state
git reset --hard origin/branch-name
```

## Pull with Rebase

```bash
# Pull and rebase instead of merge
git pull --rebase

# Set as default
git config --global pull.rebase true
```
"""
        return ScrapedDocument(
            id=self._generate_id("git-rebase"),
            url="https://git-scm.com/docs/git-rebase",
            title="Git Rebase Guide",
            content=content,
            source=self.get_source_name(),
            category="development",
            tags=["git", "rebase", "interactive"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _troubleshooting_guide(self) -> ScrapedDocument:
        """Git troubleshooting guide."""
        content = """# Git Troubleshooting Guide

## Undo Operations

### Undo Last Commit (Keep Changes)
```bash
git reset --soft HEAD~1
```

### Undo Last Commit (Discard Changes)
```bash
git reset --hard HEAD~1
```

### Undo Specific Commit (Create New Commit)
```bash
git revert commit_hash
```

### Undo Unstaged Changes
```bash
git checkout -- file.txt
git restore file.txt
```

### Undo Staged Changes
```bash
git reset HEAD file.txt
git restore --staged file.txt
```

### Undo All Local Changes
```bash
git reset --hard HEAD
git clean -fd                          # Remove untracked files
```

## Recovery

### Find Lost Commits
```bash
git reflog
git log --walk-reflogs

# Recover lost commit
git checkout commit_hash
git branch recovered commit_hash
```

### Recover Deleted Branch
```bash
git reflog
git checkout -b recovered HEAD@{N}
```

### Recover Stash
```bash
# Find lost stash
git fsck --unreachable | grep commit
git show commit_hash

# Recover
git stash apply commit_hash
```

### Recover Deleted File
```bash
# Find last commit with file
git log --all --full-history -- path/to/file

# Restore file
git checkout commit_hash^ -- path/to/file
```

## Common Errors

### "Detached HEAD"
```bash
# You're not on a branch
git checkout main                      # Go to branch
git checkout -b new-branch            # Create branch from here
```

### "Your Branch is Behind"
```bash
git pull
# Or if you want to keep local changes on top
git pull --rebase
```

### "Cannot Pull with Rebase: You Have Unstaged Changes"
```bash
git stash
git pull --rebase
git stash pop
```

### "Merge Conflict"
```bash
# View conflicted files
git status

# Edit files to resolve
# Remove conflict markers: <<<<<<<, =======, >>>>>>>

# Mark resolved
git add file.txt
git commit
```

### "Permission Denied (publickey)"
```bash
# Check SSH key
ssh -T git@github.com

# Add SSH key
ssh-add ~/.ssh/id_rsa

# Generate new key if needed
ssh-keygen -t ed25519 -C "your@email.com"
```

### "Fatal: Refusing to Merge Unrelated Histories"
```bash
git pull origin main --allow-unrelated-histories
```

### "Error: Failed to Push Some Refs"
```bash
# Pull first
git pull --rebase
git push

# Or force (if you know what you're doing)
git push --force-with-lease
```

## Clean Up

### Remove Untracked Files
```bash
git clean -n                           # Dry run
git clean -f                           # Remove files
git clean -fd                          # Include directories
git clean -fX                          # Only ignored files
```

### Garbage Collection
```bash
git gc
git gc --aggressive
```

### Prune Old Objects
```bash
git prune
git remote prune origin
```
"""
        return ScrapedDocument(
            id=self._generate_id("git-troubleshooting"),
            url="synthetic://git-troubleshooting",
            title="Git Troubleshooting Guide",
            content=content,
            source=self.get_source_name(),
            category="troubleshooting",
            tags=["git", "troubleshooting", "recovery"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "troubleshooting", "priority": "high"}
        )
    
    def _workflows_guide(self) -> ScrapedDocument:
        """Git workflows guide."""
        content = """# Git Workflows Guide

## Git Flow

### Branches
- **main**: Production-ready code
- **develop**: Integration branch
- **feature/**: New features
- **release/**: Release preparation
- **hotfix/**: Production fixes

### Feature Development
```bash
git checkout develop
git checkout -b feature/new-feature
# Work on feature
git add .
git commit -m "Add feature"
git checkout develop
git merge --no-ff feature/new-feature
git branch -d feature/new-feature
```

### Release
```bash
git checkout develop
git checkout -b release/1.0.0
# Final fixes, bump version
git checkout main
git merge --no-ff release/1.0.0
git tag -a v1.0.0 -m "Version 1.0.0"
git checkout develop
git merge --no-ff release/1.0.0
git branch -d release/1.0.0
```

### Hotfix
```bash
git checkout main
git checkout -b hotfix/fix-bug
# Fix bug
git checkout main
git merge --no-ff hotfix/fix-bug
git tag -a v1.0.1
git checkout develop
git merge --no-ff hotfix/fix-bug
git branch -d hotfix/fix-bug
```

## GitHub Flow (Simpler)

### Process
1. Create branch from main
2. Add commits
3. Open pull request
4. Review and discuss
5. Merge to main
6. Delete branch

```bash
git checkout main
git pull
git checkout -b feature/my-feature
# Work
git push -u origin feature/my-feature
# Create PR on GitHub
# After merge
git checkout main
git pull
git branch -d feature/my-feature
```

## Trunk-Based Development

### Rules
- Short-lived branches (< 2 days)
- Small, frequent commits
- Feature flags for incomplete work

```bash
git checkout main
git pull
git checkout -b short-lived-feature
# Small change
git commit -m "Small change"
git push -u origin short-lived-feature
# Quick PR, merge same day
```

## Commit Message Conventions

### Format
```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types
- **feat**: New feature
- **fix**: Bug fix
- **docs**: Documentation
- **style**: Formatting
- **refactor**: Code restructure
- **test**: Tests
- **chore**: Maintenance

### Examples
```
feat(auth): add OAuth2 login

Add OAuth2 login support for Google and GitHub.

Closes #123
```

```
fix(api): handle null response

The API was crashing when receiving null responses.
Added null check before processing.

Fixes #456
```

## Pull Request Best Practices

1. **Keep PRs small** (< 400 lines)
2. **One concern per PR**
3. **Write descriptive titles**
4. **Add context in description**
5. **Request specific reviewers**
6. **Respond to feedback promptly**
7. **Squash commits before merge** (optional)

## Code Review Checklist

- [ ] Code works as intended
- [ ] Tests pass
- [ ] No obvious bugs
- [ ] Follows style guide
- [ ] No security issues
- [ ] Documentation updated
- [ ] No unnecessary changes
"""
        return ScrapedDocument(
            id=self._generate_id("git-workflows"),
            url="synthetic://git-workflows",
            title="Git Workflows Guide",
            content=content,
            source=self.get_source_name(),
            category="development",
            tags=["git", "workflow", "gitflow", "github"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "medium"}
        )
    
    def _generate_id(self, name: str) -> str:
        """Generate document ID."""
        import hashlib
        return hashlib.md5(f"git-docs:{name}".encode()).hexdigest()[:16]


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate Git documentation")
    parser.add_argument("--output-dir", default="data/linux/git-docs")
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
    
    config = ScraperConfig(output_dir=Path(args.output_dir))
    scraper = GitDocsScraper(config)
    
    docs = scraper.scrape()
    scraper.save_documents(docs, "git_docs.jsonl")
