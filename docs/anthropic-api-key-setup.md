# Anthropic API Key — Setup & Rotation

End-to-end runbook for adding or rotating the Anthropic Claude API key
that backs the asterisk scanner and the marketing-automation app.

**Current status (as of initial setup 2026-04-17):** Key is live in prod.
Workspace `sams-collectibles-app`, key named `sc4-production`, $5 credit
funded, stored in 1Password under `API Credentials → Claude sc4-production-key`.

## Where the key is used

| Component | How it reads the key |
|---|---|
| `src/ebay_manager/services/asterisk_scanner.py` | `settings.ANTHROPIC_API_KEY` |
| Marketing automation app (planned) | `settings.ANTHROPIC_API_KEY` |
| Settings loader | `src/samscollectibles/settings/base.py` → `ANTHROPIC_API_KEY = config('ANTHROPIC_API_KEY', default='')` |
| Ansible env template | `ansible/roles/app/templates/env.production.j2` → `{{ vault_anthropic_api_key | default('') }}` |
| Encrypted vault | `ansible/group_vars/vault.yml` → `vault_anthropic_api_key` |
| 1Password | `API Credentials → Claude sc4-production-key` |

If the vault value is empty the app still boots — both the asterisk scanner
and the marketing generator degrade gracefully with a clean log line
("No ANTHROPIC_API_KEY configured").

## First-time setup (completed)

Kept for reference. Skip to "Rotate the key" below for future rotations.

### 1. Create the key in the Anthropic console

1. Go to https://console.anthropic.com → sign in.
2. Create a workspace dedicated to the app (optional but recommended for cost isolation):
   - **Workspaces** → **+ Create workspace** → name `sams-collectibles-app`.
3. Switch to that workspace, then **API keys** → **+ Create key**:
   - Name: `sc4-production`
   - Workspace dropdown: `sams-collectibles-app`
4. **Copy the key immediately** — `sk-ant-api03-…`. It's shown once.
5. **Billing** → **Add credit** → $5 (usually 3–5 months for low-volume usage).

### 2. Save to 1Password

Create an `API Credential` item:

| Field | Value |
|---|---|
| Title | `Claude sc4-production-key API` |
| type | **Bearer Token** |
| credential | the `sk-ant-api03-…` string |
| hostname | `api.anthropic.com` |
| username | `sams-collectibles-app` (workspace name, for future reference) |
| notes | workspace, purpose, creation date, initial credit, vault var name |
| tags | `anthropic`, `production`, `sc4` |

Leave `filename`, `valid from`, `expires` blank. Anthropic keys don't
expire until revoked; you can set `expires` to 1 year out as a
self-imposed rotation reminder (1Password Watchtower will surface it).

#### Which type should I pick?

- **Bearer Token** — opaque string used as `Authorization: Bearer …` or
  `x-api-key: …` in an HTTP header. Anthropic, OpenAI, GitHub PATs,
  Stripe — most modern REST APIs. ✅ this case.
- **JSON Web Token** — structured `header.payload.signature` string.
  Google ID tokens, Auth0 access tokens. Not this case.
- **JSON Credentials** — JSON blob with multiple fields, usually a file.
  Google Cloud service accounts. Not this case.
- **Other** — escape hatch. Only use if the API doesn't fit the above.

### 3. Merge the wiring PR

The env-template and vault-example changes ship as a normal PR against
`main`. Example: [PR #6](https://github.com/samrogers-com/sc4/pull/6).

```bash
gh pr checks <PR>                                # wait for CI green
gh pr merge <PR> --squash --delete-branch
git checkout main && git pull
```

### 4. Add the secret to the encrypted vault

```bash
cd /Users/samrogers/Claude/sc4/ansible
ansible-vault edit group_vars/vault.yml
```

- Vault password auto-loads from `~/.vault_pass` (configured in
  `ansible/ansible.cfg`) — no prompt.
- Decrypted in-memory in your `$EDITOR`.
- Add or update this line anywhere in the file:

  ```yaml
  vault_anthropic_api_key: sk-ant-api03-REPLACE-WITH-REAL-KEY
  ```

- Save and exit. Ansible re-encrypts automatically on close.

**Verify the file stays encrypted on disk:**

```bash
head -1 group_vars/vault.yml
# should print: $ANSIBLE_VAULT;1.1;AES256
```

If you see plain-text YAML, something went wrong — re-run
`ansible-vault encrypt group_vars/vault.yml` before committing
anything.

### 5. Deploy

```bash
cd /Users/samrogers/Claude/sc4/ansible
ansible-playbook -i inventory.ini playbooks/deploy.yml
```

Ansible pulls `main` on the VPS, re-renders the env file from the
template (now including `ANTHROPIC_API_KEY=…`), and rebuilds the
Docker container.

Expected tail of the run:

```
PLAY RECAP *****************************************************
samscollectibles : ok=8 changed=3 unreachable=0 failed=0
```

### 6. Verify in prod

**Container env var:**

```bash
ssh sams-collectibles 'docker exec src-web-1 printenv ANTHROPIC_API_KEY'
# prints sk-ant-api03-...
```

**Django settings integration:**

```bash
ssh sams-collectibles 'docker exec src-web-1 python manage.py shell -c \
  "from ebay_manager.services import asterisk_scanner; \
   print(asterisk_scanner.settings.ANTHROPIC_API_KEY[:15] + \"...\")"'
# prints sk-ant-api03-...
```

If both return the key prefix, you're live.

## Rotate the key

Do this any time the key might be compromised (shared in a log, screenshot,
scripting mistake, or annually as hygiene). Zero downtime — new key takes
over before old one is revoked.

### Rotation steps

1. **Create a new key** in the Anthropic console → same workspace
   (`sams-collectibles-app`) → name with a version suffix, e.g.
   `sc4-production-v2`. Copy the new value.

2. **Update 1Password**: edit the existing `Claude sc4-production-key API`
   item, replace the `credential` field, update `notes` with the new
   rotation date.

3. **Update the vault**:

   ```bash
   cd /Users/samrogers/Claude/sc4/ansible
   ansible-vault edit group_vars/vault.yml
   # update vault_anthropic_api_key to the new value
   ```

4. **Deploy**:

   ```bash
   ansible-playbook -i inventory.ini playbooks/deploy.yml
   ```

5. **Verify** the new prefix is live in the container (step 6 above).

6. **Revoke the old key** in the Anthropic console — API keys page →
   three-dot menu → **Revoke**. Do this ONLY after the new key is
   verified live.

### Rollback (if the new key breaks)

If the new key stops working for some reason (rate limits on a new
workspace, for example), quickly revert:

```bash
cd /Users/samrogers/Claude/sc4/ansible
ansible-vault edit group_vars/vault.yml
# put the old key back (get it from 1Password's version history)
ansible-playbook -i inventory.ini playbooks/deploy.yml
```

If you already revoked the old key, you'll need to create yet another
new one and retry.

## Troubleshooting

### `ansible-vault` errors out with "Decryption failed"

Check `~/.vault_pass` exists and matches the password used to encrypt
`group_vars/vault.yml` originally. The password file is referenced in
`ansible/ansible.cfg`.

### `printenv ANTHROPIC_API_KEY` in the container returns empty

Possible causes:

- The vault edit didn't save (`vault_anthropic_api_key` still missing or
  blank). Re-run `ansible-vault edit` and check.
- The env template didn't pick up the variable. Verify on disk:

  ```bash
  grep ANTHROPIC ansible/roles/app/templates/env.production.j2
  ```

  If empty, the template wiring PR wasn't merged. Merge it, pull main, redeploy.
- The container didn't restart. `docker compose ps` should show a
  recent `CREATED` timestamp for `src-web-1` after the deploy.

### Asterisk scanner logs "No ANTHROPIC_API_KEY configured"

The container env has the var but Django isn't seeing it. Check:

```bash
ssh sams-collectibles 'docker exec src-web-1 python manage.py shell -c \
  "from django.conf import settings; print(repr(settings.ANTHROPIC_API_KEY[:15]))"'
```

If this returns `''` but `printenv` shows the key, the Django settings
loader isn't reading the env file. The loader uses
`decouple.RepositoryEnv` against `/usr/src/app/samscollectibles/.env.production` —
make sure that file exists in the container and contains the line.

### Billing alerts

Add a notification in the Anthropic console → **Billing** → **Usage
alerts** → set a threshold at, say, $5 total per month. An email alert
fires when you cross it.
