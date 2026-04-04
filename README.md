# Sam's Collectibles

eBay store automation and management for non-sport trading cards, comic books, and posters.

## What's in this repo

- **`ebay_automation/`** — Python pipeline for inventory tracking, sold price lookup, and bulk CSV generation for eBay Seller Hub
- **`ebay_descriptions/`** — Branded HTML listing descriptions by product type and franchise
- **`ebay_uploads/`** — Product photos organized for upload (Boxes, Packs, Singles, Binders, Sets)
- **`csvs/`** — Active listing reports, upload CSVs, and templates
- **`src/`** — Django web app (store dashboard), Dockerized with Gunicorn + PostgreSQL
- **`ansible/`** — Ansible playbooks for provisioning and deploying to Hostinger VPS

## Hosting stack

Hostinger VPS (Docker) · Cloudflare DNS/SSL/CDN · Cloudflare R2 (media storage)

## Deployment

See [`DEPLOYMENT.md`](DEPLOYMENT.md) for the full guide.

```bash
# First-time server setup
ansible-playbook ansible/playbooks/provision.yml -u root --ask-vault-pass

# Deploy a code update
ansible-playbook ansible/playbooks/deploy.yml --ask-vault-pass
```

## Secrets

All secrets are managed with Ansible Vault. Copy `ansible/group_vars/vault.yml.example` to `vault.yml`, fill in real values, then encrypt:

```bash
ansible-vault encrypt ansible/group_vars/vault.yml
```
