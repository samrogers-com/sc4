# Development Workflow

How code gets from your editor to production for `samscollectibles.net`.

## The short version

```bash
# 1. Branch
git checkout -b fix/short-slug

# 2. Change code, commit (tests run locally if relevant)
git add <specific-files>            # never -A
git commit -m "Descriptive message"

# 3. Push branch, open PR
git push -u origin fix/short-slug
gh pr create --title "…" --body "…"

# 4. Wait for CI green, then merge
gh pr merge <N> --squash --delete-branch

# 5. Deploy
git checkout main && git pull
cd ansible && ansible-playbook playbooks/deploy.yml
```

## Branch naming

One logical change per branch. Prefix tells the reader the intent:

| Prefix | Use for |
|---|---|
| `feat/` | New feature or capability |
| `fix/` | Bug fix |
| `chore/` | Refactor, cleanup, deps |
| `docs/` | Documentation only |
| `ci/` | CI / workflow config |

Example: `fix/delete-variant-error-handling`, `feat/pre-1990-set-listings`, `ci/github-actions-tests`.

**Never push directly to `main`.** Branch protection enforces this; even if you bypass as admin, it disrupts the review + CI trail.

## CI — GitHub Actions

Workflow file: [`.github/workflows/test.yml`](../.github/workflows/test.yml)

### Triggers
- Every push to `main`
- Every pull request targeting `main`

### What it does
1. Ubuntu-latest runner, Python 3.12 (matches production `src/Dockerfile`)
2. `pip install -r src/requirements.txt` (with pip cache)
3. Writes a dummy `samscollectibles/.env.local` so `decouple.RepositoryEnv` can load — tests don't touch email, R2, or eBay, so dummy values are safe
4. `python manage.py check` (catches missing migrations, bad URLconf, broken imports)
5. `python manage.py test --verbosity 2`

Result appears as a **`Django tests / test`** status check on every PR. ~20–30 s end-to-end.

### Adding coverage
Tests live alongside each app at `src/<app>/tests.py`. Anything added there is picked up automatically — no workflow edits needed. See `src/ebay_manager/tests.py` for the pattern used for `_delete_variant_on_ebay` (mocked `requests`, factory for mock `Response` objects).

Run locally against the prod container (when you have it running):
```bash
ssh sams-collectibles 'docker exec src-web-1 python manage.py test ebay_manager -v 2'
```

## Branch protection on `main`

Configured via `gh api repos/samrogers-com/sc4/branches/main/protection`. Current rules:

| Rule | Setting | Why |
|---|---|---|
| Required status check | `test` must be green | Red CI blocks merge |
| Strict (up-to-date branch) | On | Branch must be rebased / merged against current `main` before merging — prevents "green on stale main, broken on new main" |
| Force pushes | Disabled | Nobody can rewrite `main`'s history |
| Branch deletion | Disabled | Can't accidentally delete `main` |
| Required conversation resolution | On | All PR comments must be resolved before merge |
| PR review required | Off | Solo dev — a self-review requirement would block every merge |
| Enforce on admins | Off | Repo owner can bypass in an emergency |

### Admin override (rare)
If CI is broken for unrelated reasons (e.g. GitHub-side outage) and you need to ship a hotfix:
```bash
gh pr merge <N> --admin --squash --delete-branch
```
Use sparingly — breaks the trail that "everything on `main` passed CI."

### Re-applying the rules (if the config drifts)
Save this request body to apply the same config again via `gh api ... --method PUT --input -`:

```json
{
  "required_status_checks": { "strict": true, "contexts": ["test"] },
  "enforce_admins": false,
  "required_pull_request_reviews": null,
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_conversation_resolution": true,
  "required_linear_history": false,
  "block_creations": false,
  "lock_branch": false,
  "allow_fork_syncing": false
}
```

If the required check name changes (e.g. we add a `lint` job), add it to `required_status_checks.contexts` and reapply.

## Deploy

See [`DEPLOYMENT.md`](../DEPLOYMENT.md) for the full details. Short form:

```bash
# After merge, from repo root:
git checkout main && git pull
cd ansible && ansible-playbook playbooks/deploy.yml
```

- Vault password comes from `~/.vault_pass` (configured in `ansible/ansible.cfg`) — no prompt.
- Playbook pulls latest `main` on the VPS, rebuilds Docker containers.
- **Pushing to GitHub alone does NOT update production.** Always run the playbook.

## Troubleshooting

### CI keeps failing after a change to `settings/base.py`
The workflow writes a dummy `.env.local` with these keys: `SECRET_KEY`, `DEBUG`, `USE_POSTGRES`, `ALLOWED_HOSTS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`. If you add a new required setting (no `default=`), either give it a `default=` or add the key to the CI step in `.github/workflows/test.yml`.

### "Your branch is behind `origin/main`" after someone else merges
```bash
git fetch origin
git rebase origin/main          # or merge, if you prefer merge commits
git push --force-with-lease     # only on your feature branch, never main
```

### CI runs against Postgres in production but SQLite in tests — is that safe?
For ORM-level tests and business logic, yes. For anything that relies on Postgres-specific SQL (raw queries, JSONB operators, full-text search), add a separate CI job that spins up a Postgres service container. Currently no tests require that.

### The "push rejected, branch is behind" error happens even when local == remote
GitHub sometimes returns a stale HTTP 400 on a first-try push; retrying or fetching-then-pushing clears it. The actual branch state after the error is usually correct — verify with `git ls-remote origin <branch>` before panicking.
