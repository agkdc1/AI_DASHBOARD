#!/bin/bash
# Store Google OAuth credentials in Vault without printing to terminal.
# Run as root (needs admin AppRole).
set -euo pipefail

source /home/pi/SHINBEE/Vault/scripts/vault-env.sh
vault_approle_login /root/vault-approle-admin-role-id /root/vault-approle-admin-secret-id

read -rsp "Client ID: " client_id
echo
read -rsp "Client Secret: " client_secret
echo

vault kv put secret/shinbeeinventree/oauth \
  client_id="$client_id" \
  client_secret="$client_secret" \
  > /dev/null

echo "Stored at secret/shinbeeinventree/oauth"
