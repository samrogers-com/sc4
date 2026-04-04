# Sam's Collectibles — Deployment Guide
## Stack: Hostinger VPS + Cloudflare DNS/CDN/R2 + Docker + Ansible

---

## Architecture Overview

```
Browser → Cloudflare (DNS + Proxy + SSL + CDN)
                ↓
         Hostinger VPS (Ubuntu 22.04)
           ├── Nginx  (reverse proxy, port 80)
           └── Docker
               ├── web  (Django + Gunicorn, port 8001)
               └── db   (PostgreSQL 13)

Media/Images → Cloudflare R2
               └── media.samscollectibles.net (public CDN URL)
```

Ansible automates everything on the VPS — server setup, Docker, Nginx, and app deployment. You run one command and it handles the rest.

---

## Ansible Project Structure

```
ansible/
  ansible.cfg                          # Default config (inventory, SSH key)
  inventory.ini                        # Your VPS IP address
  group_vars/
    all.yml                            # Shared non-sensitive variables
    vault.yml                          # Encrypted secrets (ansible-vault)
    vault.yml.example                  # Template to create vault.yml from
  playbooks/
    provision.yml                      # One-time: full server setup
    deploy.yml                         # Ongoing: redeploy app after code changes
    backup.yml                         # Database backup to local machine
  roles/
    server_setup/tasks/main.yml        # User, firewall, fail2ban
    docker/tasks/main.yml              # Docker Engine + Compose plugin
    nginx/
      tasks/main.yml                   # Install + enable Nginx
      handlers/main.yml                # Reload handler
      templates/samscollectibles.conf.j2  # Nginx site config
    app/
      tasks/main.yml                   # Git pull + env file + docker compose up
      templates/
        env.production.j2              # .env.production rendered from vault
        docker-compose.production.yml.j2  # Production compose file
```

---

## Part 1 — Prerequisites (Your Local Machine)

### 1.1 Install Ansible

```bash
pip install ansible
ansible --version
```

### 1.2 Generate an SSH Key (if you don't have one)

```bash
ssh-keygen -t rsa -b 4096 -C "sam@samscollectibles"
# Accept the default path (~/.ssh/id_rsa)
```

### 1.3 Configure Your Inventory

Edit `ansible/inventory.ini` and replace `YOUR_VPS_IP` with your actual Hostinger VPS IP:

```ini
[vps]
samscollectibles ansible_host=123.456.789.0 ansible_user=sam
```

### 1.4 Configure Variables

Edit `ansible/group_vars/all.yml` and set your GitHub repo URL and branch:

```yaml
repo_url: https://github.com/YOUR_USERNAME/sc4.git
repo_branch: main
```

### 1.5 Set Up Secrets with Ansible Vault

Ansible Vault encrypts your secrets so they can be safely stored in git.

```bash
cd ansible

# Copy the example file
cp group_vars/vault.yml.example group_vars/vault.yml

# Fill in your real secrets (open in your editor)
nano group_vars/vault.yml

# Encrypt it — you'll be prompted to create a vault password
ansible-vault encrypt group_vars/vault.yml
```

Your `vault.yml` will now be encrypted. To edit it later:

```bash
ansible-vault edit group_vars/vault.yml
```

> **Never commit an unencrypted vault.yml to git.** The `.gitignore` blocks `ansible/group_vars/vault.yml` entirely as a safety net — even after encryption. If you want to store the encrypted vault in git (optional but convenient for backup), force-add it after encrypting:
> ```bash
> git add -f ansible/group_vars/vault.yml
> ```
> Always commit `vault.yml.example` (the template with no real secrets) so others know what values are needed.

---

## Part 2 — Cloudflare R2 Setup

R2 is Cloudflare's S3-compatible object storage with no egress fees. This replaces the old S3 bucket for image hosting.

### 2.1 Create the R2 Bucket

1. Log into [dash.cloudflare.com](https://dash.cloudflare.com)
2. Go to **R2 Object Storage** → **Create bucket**
3. Name: `samscollectibles` | Region: **Automatic**

### 2.2 Create an R2 API Token

1. In R2 → **Manage R2 API Tokens** → **Create API Token**
2. Permissions: **Object Read & Write** scoped to your bucket
3. Save these immediately — you won't see them again:
   - **Access Key ID** → `vault_r2_access_key_id` in vault.yml
   - **Secret Access Key** → `vault_r2_secret_access_key` in vault.yml
   - **Endpoint URL** → `vault_r2_endpoint_url` in vault.yml

### 2.3 Enable Public Access with a Custom Domain

1. Go to your bucket → **Settings** → **Public Access** → Enable
2. Go to **Custom Domains** → Add `media.samscollectibles.net`
   - Cloudflare auto-creates the DNS record since your domain is already there
3. Your public image base URL becomes: `https://media.samscollectibles.net/`

### 2.4 Migrate Existing Images from S3 to R2

The AWS CLI works against R2's S3-compatible endpoint:

```bash
pip install awscli

# Configure AWS CLI with R2 credentials
aws configure set aws_access_key_id YOUR_R2_ACCESS_KEY
aws configure set aws_secret_access_key YOUR_R2_SECRET_KEY

# Sync from old S3 bucket to R2
aws s3 sync s3://samscollectibles \
    s3://samscollectibles \
    --source-region us-west-1 \
    --endpoint-url https://YOUR_ACCOUNT_ID.r2.cloudflarestorage.com
```

After the sync, update `IMAGE_BASE_URL` in `src/samscollectibles/settings/base.py`:

```python
IMAGE_BASE_URL = "https://media.samscollectibles.net/"
```

Then do a find-and-replace across your eBay HTML listing files to replace the old S3 URL with the new R2 URL.

### 2.5 Configure Django for R2

Add to `src/requirements.txt`:

```
django-storages[s3]
boto3
```

Add `'storages'` to `INSTALLED_APPS` in `src/samscollectibles/settings/base.py`, and replace the file storage comment block with:

```python
# Cloudflare R2 storage (S3-compatible)
if config('USE_REMOTE_STORAGE', default=False, cast=bool):
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
    STATICFILES_STORAGE = 'storages.backends.s3boto3.S3StaticStorage'
    AWS_ACCESS_KEY_ID = config('R2_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = config('R2_SECRET_ACCESS_KEY')
    AWS_STORAGE_BUCKET_NAME = config('R2_BUCKET_NAME')
    AWS_S3_ENDPOINT_URL = config('R2_ENDPOINT_URL')
    AWS_S3_CUSTOM_DOMAIN = config('R2_CUSTOM_DOMAIN', default=None)
    AWS_DEFAULT_ACL = 'public-read'
    AWS_S3_OBJECT_PARAMETERS = {'CacheControl': 'max-age=86400'}
    AWS_QUERYSTRING_AUTH = False
    IMAGE_BASE_URL = f"https://{config('R2_CUSTOM_DOMAIN')}/"
```

---

## Part 3 — Hostinger VPS Selection

### Choose a Plan

Purchase a VPS on [hostinger.com](https://hostinger.com) with **Ubuntu 22.04 LTS**. For light-to-moderate use:

| Plan  | vCPU | RAM  | Storage | Price (est.) |
|-------|------|------|---------|--------------|
| KVM 1 | 1    | 4 GB | 50 GB   | ~$5/mo       |
| KVM 2 | 2    | 8 GB | 100 GB  | ~$9/mo       |

**KVM 2 is recommended** — gives headroom for growth without a big price jump.

Once provisioned, Hostinger gives you the root password and IP via email/dashboard.

### Upload Your SSH Key to the VPS

Before running Ansible, copy your public key to the VPS (Hostinger also has a UI for this in the VPS control panel):

```bash
ssh-copy-id root@YOUR_VPS_IP
```

---

## Part 4 — Run Ansible: First-Time Provision

This single command sets up the entire server — user accounts, firewall, Docker, Nginx, and deploys the app:

```bash
cd ansible

# First run uses root (Hostinger default), prompts for vault password
ansible-playbook playbooks/provision.yml -u root --ask-vault-pass
```

Ansible will run through these roles in order:

1. **server_setup** — Creates the `sam` user, configures SSH keys, enables UFW firewall (OpenSSH + Nginx), installs fail2ban
2. **docker** — Installs Docker Engine and the Compose plugin, adds `sam` to the docker group
3. **nginx** — Installs Nginx, deploys the site config from the Jinja2 template, enables the site
4. **app** — Clones the repo, writes `.env.production` from vault secrets, writes `docker-compose.production.yml`, runs `docker compose up --build`

Total run time on a fresh VPS: roughly 3–5 minutes.

---

## Part 5 — Cloudflare DNS and SSL

### 5.1 Point DNS at Your VPS

In the Cloudflare dashboard → **DNS** for `samscollectibles.net`:

| Type | Name | Content     | Proxy  |
|------|------|-------------|--------|
| A    | @    | YOUR_VPS_IP | ✅ Proxied |
| A    | www  | YOUR_VPS_IP | ✅ Proxied |

The orange cloud (proxied) gives you SSL, CDN caching, and DDoS protection.

### 5.2 SSL/TLS Mode

In Cloudflare → **SSL/TLS**:

- Mode: **Full** (Nginx only listens on HTTP internally, Cloudflare terminates HTTPS)
- Enable **Always Use HTTPS**
- Enable **Automatic HTTPS Rewrites**

No Certbot or Let's Encrypt needed — Cloudflare handles the certificate.

### 5.3 Fix Django's SSL Redirect

Since Cloudflare terminates SSL before the request reaches Nginx, `SECURE_SSL_REDIRECT = True` causes a redirect loop. Update `src/samscollectibles/settings/production.py`:

```python
SECURE_SSL_REDIRECT = False          # Cloudflare handles this
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
```

### 5.4 Optional: Cache Rules

In Cloudflare → **Caching** → **Cache Rules**, add a rule to cache static assets:

- Match: `samscollectibles.net/static/*`
- Cache TTL: 1 day

---

## Part 6 — Ongoing: Deploying Updates

After pushing code changes to GitHub, redeploy with:

```bash
cd ansible
ansible-playbook playbooks/deploy.yml --ask-vault-pass
```

This pulls the latest code, rebuilds Docker images, and restarts containers. It skips server setup and Nginx since those don't change.

---

## Part 7 — Maintenance

### Database Backup

Dumps the database and fetches it to your local `ansible/backups/` folder:

```bash
cd ansible
ansible-playbook playbooks/backup.yml
```

### Run Ad-Hoc Commands on the Server

```bash
# Check container status
ansible vps -m command -a "docker compose -f /home/sam/sams-collectibles/src/docker-compose.production.yml ps"

# View live logs
ansible vps -m command -a "docker compose -f /home/sam/sams-collectibles/src/docker-compose.production.yml logs --tail=50 web"

# Run a Django management command
ansible vps -m command -a "docker compose -f /home/sam/sams-collectibles/src/docker-compose.production.yml exec -T web python manage.py migrate"
```

### Update Secrets

If you need to rotate a password or API key:

```bash
# Edit the vault
ansible-vault edit ansible/group_vars/vault.yml

# Redeploy to apply the new values
ansible-playbook ansible/playbooks/deploy.yml --ask-vault-pass
```

---

## Quick Reference

### Ansible Commands

| Task | Command |
|------|---------|
| First-time server setup | `ansible-playbook playbooks/provision.yml -u root --ask-vault-pass` |
| Deploy code update | `ansible-playbook playbooks/deploy.yml --ask-vault-pass` |
| Backup database | `ansible-playbook playbooks/backup.yml` |
| Edit secrets | `ansible-vault edit group_vars/vault.yml` |

### Vault Variables

| Variable | Description |
|----------|-------------|
| `vault_secret_key` | Django secret key |
| `vault_db_password` | PostgreSQL password |
| `vault_r2_access_key_id` | Cloudflare R2 Access Key |
| `vault_r2_secret_access_key` | Cloudflare R2 Secret Key |
| `vault_r2_endpoint_url` | R2 endpoint URL |
| `vault_email_host_user` | Gmail address |
| `vault_email_host_password` | Gmail app password |

### group_vars/all.yml Variables

| Variable | Description |
|----------|-------------|
| `app_user` | Linux user on VPS (`sam`) |
| `app_dir` | App root on VPS |
| `repo_url` | GitHub repo URL |
| `repo_branch` | Branch to deploy (`main`) |
| `domain` | Primary domain |
| `gunicorn_workers` | Number of Gunicorn workers |
| `gunicorn_port` | Internal port (8001) |
