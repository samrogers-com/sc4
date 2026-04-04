#!/bin/bash
# setup-ssh.sh
# Run this at the start of each Cowork session to restore GitHub SSH access.
# Usage: bash setup-ssh.sh

set -e

KEY_SRC="$(dirname "$0")/.cowork/ssh/id_ed25519_github"

if [ ! -f "$KEY_SRC" ]; then
  echo "ERROR: SSH key not found at $KEY_SRC"
  exit 1
fi

mkdir -p ~/.ssh
chmod 700 ~/.ssh

cp "$KEY_SRC" ~/.ssh/id_ed25519_github
chmod 600 ~/.ssh/id_ed25519_github

cat > ~/.ssh/config << 'EOF'
Host github-samrogers-com
    HostName github.com
    User git
    IdentityFile ~/.ssh/id_ed25519_github
    IdentitiesOnly yes
EOF
chmod 600 ~/.ssh/config

echo "SSH configured. Testing connection..."
ssh -T git@github-samrogers-com 2>&1 || true
