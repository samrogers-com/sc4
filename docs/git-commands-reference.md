# Git Commands Reference

## Feature Branch Workflow (after accidentally working on main)

```bash
# 1. We were on main with uncommitted changes (oops)
git branch --show-current          # confirmed we were on main

# 2. Created a feature branch FROM main — uncommitted changes come along
#    KEY TRICK: `git checkout -b` carries uncommitted changes with you to the
#    new branch. Since the changes aren't committed yet, they belong to your
#    working directory — not to any branch. So you can create a branch
#    "after the fact" and commit there instead. Works as long as there are
#    no conflicts with the branch you're switching to.
git checkout -b feature/validation-status-field

# 3. Staged specific files (not git add -A, to avoid .env/secrets)
git add file1 file2 file3...

# 4. Committed on the feature branch
git commit -m "message"

# 5. Switched back to main and merged (fast-forward since main hadn't moved)
git checkout main
git merge feature/validation-status-field

# 6. Pushed and cleaned up
git push origin main
git branch -d feature/validation-status-field
```
