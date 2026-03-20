#!/bin/bash
# =============================================================================
# SHINBEE Unified Installer
# Reads config.yaml and deploys the full stack on a Raspberry Pi.
# Usage: ./install.sh [--phase NAME] [--config PATH] [--dry-run]
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/../config.yaml"
DRY_RUN=false
PHASE=""

# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --phase)   PHASE="$2"; shift 2 ;;
    --config)  CONFIG_FILE="$2"; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    -h|--help)
      echo "Usage: $0 [--phase NAME] [--config PATH] [--dry-run]"
      echo ""
      echo "Phases: preflight packages docker pki vault_deploy vault_init"
      echo "        vault_configure secrets gcp_wif aws_roles render"
      echo "        systemd daemon stacks firewall"
      echo "        flutter ai_assistant"
      echo ""
      echo "  --phase NAME   Run only the named phase"
      echo "  --config PATH  Path to config.yaml (default: ./config.yaml)"
      echo "  --dry-run      Print actions without executing"
      exit 0 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------
log()  { echo -e "\033[1;34m[$(date '+%H:%M:%S')]\033[0m $*"; }
ok()   { echo -e "\033[1;32m  ✓\033[0m $*"; }
warn() { echo -e "\033[1;33m  ⚠\033[0m $*"; }
err()  { echo -e "\033[1;31m  ✗\033[0m $*" >&2; }
die()  { err "$*"; exit 1; }

run() {
  if $DRY_RUN; then
    echo "  [dry-run] $*"
  else
    "$@"
  fi
}

# ---------------------------------------------------------------------------
# Config reader — requires python3 + pyyaml (both ship with Debian bookworm)
# ---------------------------------------------------------------------------
cfg() {
  python3 -c "
import yaml,sys,functools
with open('${CONFIG_FILE}') as f: c=yaml.safe_load(f)
keys=sys.argv[1].split('.')
v=functools.reduce(lambda d,k: d[int(k)] if isinstance(d,list) else d[k], keys, c)
if isinstance(v,list): print('\n'.join(str(x) for x in v))
elif isinstance(v,bool): print(str(v).lower())
else: print(v)
" "$1"
}

# ---------------------------------------------------------------------------
# Validate config file exists and parses
# ---------------------------------------------------------------------------
[[ -f "$CONFIG_FILE" ]] || die "Config file not found: $CONFIG_FILE"
python3 -c "import yaml; yaml.safe_load(open('$CONFIG_FILE'))" 2>/dev/null \
  || die "Config file is not valid YAML: $CONFIG_FILE"

REPO_ROOT="$(cfg global.repo_root)"
USER="$(cfg global.user)"

# =============================================================================
# PHASE 1: preflight
# =============================================================================
phase_preflight() {
  log "Phase 1: preflight checks"

  # Architecture
  local arch
  arch=$(uname -m)
  [[ "$arch" == "aarch64" ]] || die "Expected aarch64, got $arch"
  ok "Architecture: $arch"

  # OS
  if [[ -f /etc/os-release ]]; then
    . /etc/os-release
    [[ "$VERSION_CODENAME" == "bookworm" ]] || warn "Expected bookworm, got $VERSION_CODENAME"
    ok "OS: $PRETTY_NAME"
  fi

  # Sudo
  if [[ $EUID -ne 0 ]]; then
    sudo -n true 2>/dev/null || die "This script requires root or passwordless sudo"
  fi
  ok "Sudo: available"

  # Config validation — spot-check a few keys
  [[ -n "$(cfg gcp.project_id)" ]] || die "gcp.project_id missing from config"
  [[ -n "$(cfg vault.port)" ]]     || die "vault.port missing from config"
  [[ -n "$(cfg fax.ntt.sip_server)" ]] || die "fax.ntt.sip_server missing from config"
  ok "Config: validated"
}

# =============================================================================
# PHASE 2: packages
# =============================================================================
phase_packages() {
  log "Phase 2: installing packages"

  # apt packages
  local apt_pkgs=(
    docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    python3 python3-pip python3-venv python3-yaml
    chromium-browser chromium-chromedriver
    iptables iptables-persistent
    openssl jq curl wget gnupg lsb-release ca-certificates
    git
  )

  # Add Docker repo if not present
  if ! apt-cache policy docker-ce 2>/dev/null | grep -q 'Candidate'; then
    log "  Adding Docker apt repository..."
    run sudo install -m 0755 -d /etc/apt/keyrings
    if ! $DRY_RUN; then
      curl -fsSL https://download.docker.com/linux/debian/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg 2>/dev/null || true
      echo "deb [arch=arm64 signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian bookworm stable" \
        | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    fi
  fi

  run sudo apt-get update -qq
  run sudo apt-get install -y -qq "${apt_pkgs[@]}"
  ok "apt packages installed"

  # pip packages
  local pip_pkgs=(selenium hvac google-cloud-storage pyyaml)
  run sudo pip3 install --break-system-packages "${pip_pkgs[@]}"
  ok "pip packages installed"

  # gcloud CLI (if not installed)
  if ! command -v gcloud &>/dev/null; then
    log "  Installing gcloud CLI..."
    if ! $DRY_RUN; then
      echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
        | sudo tee /etc/apt/sources.list.d/google-cloud-sdk.list > /dev/null
      curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
        | sudo gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg 2>/dev/null || true
      sudo apt-get update -qq && sudo apt-get install -y -qq google-cloud-cli
    fi
    ok "gcloud CLI installed"
  else
    ok "gcloud CLI already installed"
  fi
}

# =============================================================================
# PHASE 3: docker
# =============================================================================
phase_docker() {
  log "Phase 3: Docker setup"

  run sudo systemctl enable --now docker
  ok "Docker service enabled"

  # Add user to docker group
  if ! id -nG "$USER" | grep -qw docker; then
    run sudo usermod -aG docker "$USER"
    ok "Added $USER to docker group"
  else
    ok "$USER already in docker group"
  fi

  # Pull base images
  local images=(
    "hashicorp/vault:$(cfg vault.version)"
    "$(cfg fax.db.image)"
  )
  for img in "${images[@]}"; do
    log "  Pulling $img..."
    run sg docker -c "docker pull $img" || run sudo docker pull "$img"
  done
  ok "Base images pulled"
}

# =============================================================================
# PHASE 4: pki
# =============================================================================
phase_pki() {
  log "Phase 4: PKI certificates"

  local pki_dir="${REPO_ROOT}/Vault/pki"
  mkdir -p "$pki_dir"

  local ca_key="${pki_dir}/ca.key"
  local ca_crt="${pki_dir}/ca.crt"
  local client_key="${pki_dir}/client.key"
  local client_crt="${pki_dir}/client.crt"

  # CA cert
  if [[ -f "$ca_crt" && -f "$ca_key" ]]; then
    ok "CA certificate already exists"
  else
    log "  Generating CA certificate..."
    if ! $DRY_RUN; then
      openssl genrsa -out "$ca_key" "$(cfg pki.ca.key_bits)"
      openssl req -new -x509 -key "$ca_key" \
        -out "$ca_crt" \
        -days "$(cfg pki.ca.validity_days)" \
        -subj "/C=$(cfg pki.ca.c)/ST=$(cfg pki.ca.st)/O=$(cfg pki.ca.o)/CN=$(cfg pki.ca.cn)" \
        -addext "basicConstraints=critical,CA:TRUE" \
        -addext "keyUsage=keyCertSign" \
        -addext "extendedKeyUsage=clientAuth"
      chmod 0400 "$ca_key"
    fi
    ok "CA certificate generated"
  fi

  # Client cert
  if [[ -f "$client_crt" && -f "$client_key" ]]; then
    ok "Client certificate already exists"
  else
    log "  Generating client certificate..."
    if ! $DRY_RUN; then
      openssl genrsa -out "$client_key" "$(cfg pki.client.key_bits)"
      openssl req -new -key "$client_key" \
        -out "${pki_dir}/client.csr" \
        -subj "/C=$(cfg pki.client.c)/ST=$(cfg pki.client.st)/O=$(cfg pki.client.o)/CN=$(cfg pki.client.cn)"
      openssl x509 -req \
        -in "${pki_dir}/client.csr" \
        -CA "$ca_crt" -CAkey "$ca_key" -CAcreateserial \
        -out "$client_crt" \
        -days "$(cfg pki.client.validity_days)" \
        -extfile <(echo "extendedKeyUsage=clientAuth")
      chmod 0400 "$client_key"
      rm -f "${pki_dir}/client.csr"
    fi
    ok "Client certificate generated"
  fi

  # WIF credential config
  log "  Writing wif-credential-config.json..."
  if ! $DRY_RUN; then
    local project_number
    project_number="$(cfg gcp.project_number)"
    local pool_id
    pool_id="$(cfg gcp.wif.pool_id)"
    local provider_id
    provider_id="$(cfg gcp.wif.provider_id)"

    cat > "${pki_dir}/wif-credential-config.json" << WIFEOF
{
  "universe_domain": "googleapis.com",
  "type": "external_account",
  "audience": "//iam.googleapis.com/projects/${project_number}/locations/global/workloadIdentityPools/${pool_id}/providers/${provider_id}",
  "subject_token_type": "urn:ietf:params:oauth:token-type:mtls",
  "token_url": "https://sts.mtls.googleapis.com/v1/token",
  "credential_source": {
    "certificate": {
      "use_default_certificate_config": true
    }
  },
  "token_info_url": "https://sts.mtls.googleapis.com/v1/introspect"
}
WIFEOF
  fi
  ok "WIF credential config written"

  # gcloud certificate_config.json (for mTLS)
  local gcloud_dir="/home/${USER}/.config/gcloud"
  log "  Writing certificate_config.json..."
  if ! $DRY_RUN; then
    mkdir -p "$gcloud_dir"
    cat > "${gcloud_dir}/certificate_config.json" << CERTCFGEOF
{
  "cert_configs": {
    "workload": {
      "cert_path": "${client_crt}",
      "key_path": "${client_key}"
    }
  }
}
CERTCFGEOF
    chown -R "${USER}:${USER}" "$gcloud_dir"
  fi
  ok "gcloud certificate config written"

  # AWS Roles Anywhere certificate_config.json
  log "  Writing AWS certificate_config.json..."
  if ! $DRY_RUN; then
    cat > "${pki_dir}/certificate_config.json" << AWSCERTEOF
{
  "trust_anchor_arn": "$(cfg aws.roles_anywhere.trust_anchor_arn)",
  "profile_arn": "$(cfg aws.roles_anywhere.profile_arn)",
  "role_arn": "$(cfg aws.roles_anywhere.role_arn)",
  "certificate_path": "${client_crt}",
  "private_key_path": "${client_key}"
}
AWSCERTEOF
  fi
  ok "AWS certificate config written"
}

# =============================================================================
# PHASE 5: vault_deploy
# =============================================================================
phase_vault_deploy() {
  log "Phase 5: Vault deployment"

  local vault_dir="${REPO_ROOT}/Vault"
  mkdir -p "${vault_dir}/data" "${vault_dir}/logs"

  # vault.hcl
  log "  Generating vault.hcl..."
  if ! $DRY_RUN; then
    cat > "${vault_dir}/vault.hcl" << 'VHCLEOF'
storage "file" {
  path = "/vault/data"
}

listener "tcp" {
  address     = "0.0.0.0:VAULT_PORT"
  tls_disable = 1
}

seal "gcpckms" {
  project    = "GCP_PROJECT"
  region     = "GCP_REGION"
  key_ring   = "KMS_KEY_RING"
  crypto_key = "KMS_CRYPTO_KEY"
}

api_addr     = "VAULT_API_ADDR"
cluster_addr = "http://127.0.0.1:8201"

ui = true

disable_mlock = true

log_level = "VAULT_LOG_LEVEL"
VHCLEOF
    # Substitute values
    sed -i "s|VAULT_PORT|$(cfg vault.port)|g" "${vault_dir}/vault.hcl"
    sed -i "s|GCP_PROJECT|$(cfg gcp.project_id)|g" "${vault_dir}/vault.hcl"
    sed -i "s|GCP_REGION|$(cfg gcp.region)|g" "${vault_dir}/vault.hcl"
    sed -i "s|KMS_KEY_RING|$(cfg gcp.kms.key_ring)|g" "${vault_dir}/vault.hcl"
    sed -i "s|KMS_CRYPTO_KEY|$(cfg gcp.kms.crypto_key)|g" "${vault_dir}/vault.hcl"
    sed -i "s|VAULT_API_ADDR|$(cfg vault.address)|g" "${vault_dir}/vault.hcl"
    sed -i "s|VAULT_LOG_LEVEL|$(cfg vault.log_level)|g" "${vault_dir}/vault.hcl"
  fi
  ok "vault.hcl generated"

  # docker-compose.yml
  log "  Generating Vault docker-compose.yml..."
  if ! $DRY_RUN; then
    local vault_port
    vault_port="$(cfg vault.port)"
    local vault_version
    vault_version="$(cfg vault.version)"
    local container_name
    container_name="$(cfg vault.container_name)"

    cat > "${vault_dir}/docker-compose.yml" << DCEOF
services:
  vault:
    image: hashicorp/vault:${vault_version}
    container_name: ${container_name}
    restart: unless-stopped
    ports:
      - "127.0.0.1:${vault_port}:${vault_port}"
    user: root
    cap_add:
      - IPC_LOCK
    environment:
      VAULT_ADDR: "http://127.0.0.1:${vault_port}"
      GOOGLE_APPLICATION_CREDENTIALS: "/vault/gcp-kms-sa.json"
    volumes:
      - ./vault.hcl:/vault/config/vault.hcl:ro
      - ./data:/vault/data
      - ./logs:/vault/logs
      - ./data/gcp-kms-sa.json:/vault/gcp-kms-sa.json:ro
    command: vault server -config=/vault/config/vault.hcl
    healthcheck:
      test: ["CMD", "vault", "status", "-address=http://127.0.0.1:${vault_port}"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 10s
DCEOF
  fi
  ok "Vault docker-compose.yml generated"

  # Check for KMS SA key
  local sa_key="${vault_dir}/data/gcp-kms-sa.json"
  if [[ ! -f "$sa_key" ]]; then
    if $DRY_RUN; then
      warn "GCP KMS service account key missing: $sa_key (dry-run, continuing)"
    else
      warn "GCP KMS service account key missing: $sa_key"
      echo ""
      echo "  Please copy your GCP KMS service account JSON key to:"
      echo "    $sa_key"
      echo ""
      echo "  Then ensure it's readable by UID 100 (Vault container):"
      echo "    sudo chown 100:100 $sa_key"
      echo ""
      read -rp "  Press Enter once the key is in place (or Ctrl-C to abort)..."
      [[ -f "$sa_key" ]] || die "KMS SA key still missing: $sa_key"
    fi
  fi
  if ! $DRY_RUN; then
    sudo chown 100:100 "$sa_key" 2>/dev/null || true
  fi
  ok "KMS SA key present"

  # Start Vault
  log "  Starting Vault container..."
  run sg docker -c "docker compose -f ${vault_dir}/docker-compose.yml up -d" \
    || run sudo docker compose -f "${vault_dir}/docker-compose.yml" up -d

  # Wait for healthy
  log "  Waiting for Vault to be ready..."
  if ! $DRY_RUN; then
    for i in $(seq 1 30); do
      if vault status -address="$(cfg vault.address)" &>/dev/null; then
        break
      fi
      sleep 2
    done
    vault status -address="$(cfg vault.address)" &>/dev/null || die "Vault did not become ready"
  fi
  ok "Vault is running"
}

# =============================================================================
# PHASE 6: vault_init
# =============================================================================
phase_vault_init() {
  log "Phase 6: Vault initialization"

  export VAULT_ADDR="$(cfg vault.address)"

  # Check if already initialized
  if vault status -format=json 2>/dev/null | python3 -c "
import sys,json
d=json.load(sys.stdin)
sys.exit(0 if d.get('initialized',False) else 1)
" 2>/dev/null; then
    ok "Vault already initialized"
    return
  fi

  log "  Initializing Vault (GCP KMS auto-unseal)..."
  if $DRY_RUN; then
    echo "  [dry-run] vault operator init -recovery-shares=5 -recovery-threshold=3"
    return
  fi

  local init_output
  init_output=$(vault operator init -recovery-shares=5 -recovery-threshold=3 -format=json)

  # Save root token temporarily
  local root_token
  root_token=$(echo "$init_output" | python3 -c "import sys,json; print(json.load(sys.stdin)['root_token'])")
  printf '%s' "$root_token" | sudo tee /root/vault-root-token > /dev/null
  sudo chmod 0400 /root/vault-root-token

  echo ""
  echo "  ============================================================"
  echo "  VAULT INITIALIZED — SAVE THESE RECOVERY KEYS IMMEDIATELY"
  echo "  ============================================================"
  echo "$init_output" | python3 -c "
import sys,json
d=json.load(sys.stdin)
for i,k in enumerate(d['recovery_keys_b64'],1):
    print(f'  Recovery Key {i}: {k}')
print(f'  Root Token:      {d[\"root_token\"]}')
"
  echo "  ============================================================"
  echo ""
  echo "  Root token saved to /root/vault-root-token (0400)"
  echo "  Save recovery keys to your password manager NOW."
  echo ""
  read -rp "  Press Enter once you have saved the recovery keys..."
  ok "Vault initialized"
}

# =============================================================================
# PHASE 7: vault_configure
# =============================================================================
phase_vault_configure() {
  log "Phase 7: Vault configuration (policies, AppRole)"

  export VAULT_ADDR="$(cfg vault.address)"

  if $DRY_RUN; then
    echo "  [dry-run] Would enable KV v2, write policies, enable AppRole, create roles"
    return
  fi

  # Get root token
  if sudo test -f /root/vault-root-token; then
    export VAULT_TOKEN
    VAULT_TOKEN=$(sudo cat /root/vault-root-token)
  else
    die "Root token not found at /root/vault-root-token. Run vault_init phase first."
  fi

  # Enable KV v2 (idempotent)
  log "  Enabling KV v2 secrets engine..."
  vault secrets enable -path=secret -version=2 kv 2>/dev/null || true
  ok "KV v2 enabled at secret/"

  # Write policies
  local policy_dir="${REPO_ROOT}/Vault/policies"
  for pol_file in "${policy_dir}"/*.hcl; do
    local pol_name
    pol_name=$(basename "$pol_file" .hcl)
    log "  Writing policy: $pol_name"
    run vault policy write "$pol_name" "$pol_file"
  done
  ok "Policies written"

  # Enable AppRole (idempotent)
  log "  Enabling AppRole auth..."
  vault auth enable approle 2>/dev/null || true
  ok "AppRole auth enabled"

  # Create AppRole roles
  local roles=("shinbee_japan_fax" "shinbeeinventree" "admin" "rakuten" "daemon")
  local role_configs=("fax" "inventree" "admin" "rakuten" "daemon")

  for i in "${!roles[@]}"; do
    local role_name="${roles[$i]}"
    local cfg_key="${role_configs[$i]}"
    local role_id_path
    role_id_path="$(cfg vault.approle.${cfg_key}.role_id_path)"
    local secret_id_path
    secret_id_path="$(cfg vault.approle.${cfg_key}.secret_id_path)"

    log "  Creating AppRole: $role_name"
    vault write "auth/approle/role/${role_name}" \
      token_policies="${role_name}" \
      token_ttl=1h \
      token_max_ttl=4h \
      secret_id_ttl=0

    # Write role-id
    local role_id
    role_id=$(vault read -field=role_id "auth/approle/role/${role_name}/role-id")
    printf '%s' "$role_id" | sudo tee "$role_id_path" > /dev/null
    sudo chmod 0400 "$role_id_path"
    sudo chown root:root "$role_id_path"

    # Write secret-id
    local secret_id
    secret_id=$(vault write -field=secret_id -f "auth/approle/role/${role_name}/secret-id")
    printf '%s' "$secret_id" | sudo tee "$secret_id_path" > /dev/null
    sudo chmod 0400 "$secret_id_path"
    sudo chown root:root "$secret_id_path"

    ok "AppRole $role_name created → $role_id_path, $secret_id_path"
  done
}

# =============================================================================
# PHASE 8: secrets
# =============================================================================
phase_secrets() {
  log "Phase 8: Vault secrets population"

  export VAULT_ADDR="$(cfg vault.address)"

  if $DRY_RUN; then
    echo "  [dry-run] Would prompt for all secret values and write to Vault"
    return
  fi

  if sudo test -f /root/vault-root-token; then
    export VAULT_TOKEN
    VAULT_TOKEN=$(sudo cat /root/vault-root-token)
  else
    die "Root token not found. Run vault_init phase first."
  fi

  echo ""
  echo "  This phase writes secrets to Vault."
  echo "  For each secret, enter the value when prompted."
  echo "  Leave blank to skip (if already populated)."
  echo ""

  prompt_secret() {
    local path="$1" field="$2" description="$3"
    local current
    current=$(vault kv get -field="$field" "$path" 2>/dev/null || true)
    if [[ -n "$current" ]]; then
      ok "$path.$field already set"
      return
    fi
    local value
    read -rsp "  Enter ${description}: " value
    echo ""
    if [[ -n "$value" ]]; then
      vault kv patch "$path" "${field}=${value}" 2>/dev/null \
        || vault kv put "$path" "${field}=${value}"
      ok "$path.$field written"
    else
      warn "$path.$field skipped"
    fi
  }

  # fax/db (Vault path: secret/shinbee_japan_fax/db)
  log "  Fax database secrets..."
  local fax_db_exists
  fax_db_exists=$(vault kv get -format=json secret/shinbee_japan_fax/db 2>/dev/null || echo "")
  if [[ -z "$fax_db_exists" ]]; then
    local db_root_pass db_pass
    read -rsp "  MySQL root password: " db_root_pass; echo
    read -rsp "  MySQL user password: " db_pass; echo
    vault kv put secret/shinbee_japan_fax/db \
      mysql_root_password="$db_root_pass" \
      mysql_database="$(cfg fax.db.name)" \
      mysql_user="$(cfg fax.db.user)" \
      mysql_password="$db_pass"
    ok "secret/shinbee_japan_fax/db written"
  else
    ok "secret/shinbee_japan_fax/db already exists"
  fi

  # fax/ami (Vault path: secret/shinbee_japan_fax/ami)
  log "  AMI secrets..."
  local ami_exists
  ami_exists=$(vault kv get -format=json secret/shinbee_japan_fax/ami 2>/dev/null || echo "")
  if [[ -z "$ami_exists" ]]; then
    local ami_secret
    read -rsp "  AMI secret (password): " ami_secret; echo
    vault kv put secret/shinbee_japan_fax/ami \
      username="$(cfg fax.ami.username)" \
      secret="$ami_secret"
    ok "secret/shinbee_japan_fax/ami written"
  else
    ok "secret/shinbee_japan_fax/ami already exists"
  fi

  # fax/api-key (Vault path: secret/shinbee_japan_fax/fax)
  log "  Fax API key..."
  local fax_exists
  fax_exists=$(vault kv get -format=json secret/shinbee_japan_fax/fax 2>/dev/null || echo "")
  if [[ -z "$fax_exists" ]]; then
    local api_key
    read -rsp "  Fax API key: " api_key; echo
    vault kv put secret/shinbee_japan_fax/fax api_key="$api_key"
    ok "secret/shinbee_japan_fax/fax written"
  else
    ok "secret/shinbee_japan_fax/fax already exists"
  fi

  # fax/switch (Vault path: secret/shinbee_japan_fax/switch)
  log "  Switch secrets..."
  local switch_exists
  switch_exists=$(vault kv get -format=json secret/shinbee_japan_fax/switch 2>/dev/null || echo "")
  if [[ -z "$switch_exists" ]]; then
    local switch_pass
    read -rsp "  Switch password: " switch_pass; echo
    vault kv put secret/shinbee_japan_fax/switch password="$switch_pass"
    ok "secret/shinbee_japan_fax/switch written"
  else
    ok "secret/shinbee_japan_fax/switch already exists"
  fi

  # fax/aws (Vault path: secret/shinbee_japan_fax/aws)
  log "  Fax AWS credentials..."
  local fax_aws_exists
  fax_aws_exists=$(vault kv get -format=json secret/shinbee_japan_fax/aws 2>/dev/null || echo "")
  if [[ -z "$fax_aws_exists" ]]; then
    local aws_key aws_secret
    read -rp  "  AWS Access Key ID: " aws_key
    read -rsp "  AWS Secret Access Key: " aws_secret; echo
    vault kv put secret/shinbee_japan_fax/aws \
      access_key_id="$aws_key" \
      secret_access_key="$aws_secret"
    ok "secret/shinbee_japan_fax/aws written"
  else
    ok "secret/shinbee_japan_fax/aws already exists"
  fi

  # fax/terraform (Vault path: secret/shinbee_japan_fax/terraform)
  log "  Terraform email password..."
  local tf_exists
  tf_exists=$(vault kv get -format=json secret/shinbee_japan_fax/terraform 2>/dev/null || echo "")
  if [[ -z "$tf_exists" ]]; then
    local email_pass
    read -rsp "  Email app password (for terraform notifications): " email_pass; echo
    vault kv put secret/shinbee_japan_fax/terraform email_password="$email_pass"
    ok "secret/shinbee_japan_fax/terraform written"
  else
    ok "secret/shinbee_japan_fax/terraform already exists"
  fi

  # inventree/db (Vault path: secret/shinbeeinventree/db)
  log "  InvenTree database secret..."
  local inv_db_exists
  inv_db_exists=$(vault kv get -format=json secret/shinbeeinventree/db 2>/dev/null || echo "")
  if [[ -z "$inv_db_exists" ]]; then
    local inv_pass
    read -rsp "  InvenTree MySQL password: " inv_pass; echo
    vault kv put secret/shinbeeinventree/db mysql_password="$inv_pass"
    ok "secret/shinbeeinventree/db written"
  else
    ok "secret/shinbeeinventree/db already exists"
  fi

  # inventree/aws (Vault path: secret/shinbeeinventree/aws)
  log "  InvenTree AWS credentials..."
  local inv_aws_exists
  inv_aws_exists=$(vault kv get -format=json secret/shinbeeinventree/aws 2>/dev/null || echo "")
  if [[ -z "$inv_aws_exists" ]]; then
    local inv_aws_key inv_aws_secret
    read -rp  "  InvenTree AWS Access Key ID: " inv_aws_key
    read -rsp "  InvenTree AWS Secret Access Key: " inv_aws_secret; echo
    vault kv put secret/shinbeeinventree/aws \
      access_key_id="$inv_aws_key" \
      secret_access_key="$inv_aws_secret"
    ok "secret/shinbeeinventree/aws written"
  else
    ok "secret/shinbeeinventree/aws already exists"
  fi

  # system/backup — encryption password for unified backup
  log "  Backup encryption password..."
  local backup_exists
  backup_exists=$(vault kv get -format=json secret/system/backup 2>/dev/null || echo "")
  if [[ -z "$backup_exists" ]]; then
    local backup_pass
    read -rp "  Auto-generate backup encryption password? (Y/n): " gen_choice
    if [[ "$gen_choice" == "n" || "$gen_choice" == "N" ]]; then
      read -rsp "  Enter backup encryption password: " backup_pass; echo
    else
      backup_pass=$(openssl rand -base64 32)
      echo "  Generated password: $backup_pass"
      echo "  SAVE THIS PASSWORD — it is needed to restore backups."
    fi
    if [[ -n "$backup_pass" ]]; then
      vault kv put secret/system/backup encryption_password="$backup_pass"
      ok "secret/system/backup written"
    else
      warn "secret/system/backup skipped"
    fi
  else
    ok "secret/system/backup already exists"
  fi

  # Revoke root token
  echo ""
  read -rp "  Revoke root token now? (y/N): " revoke_choice
  if [[ "$revoke_choice" == "y" || "$revoke_choice" == "Y" ]]; then
    vault token revoke -self
    sudo rm -f /root/vault-root-token
    ok "Root token revoked and deleted"
  else
    warn "Root token NOT revoked — do this manually when ready"
  fi
}

# =============================================================================
# PHASE 9: gcp_wif
# =============================================================================
phase_gcp_wif() {
  log "Phase 9: GCP Workload Identity Federation"

  local project_id
  project_id="$(cfg gcp.project_id)"
  local project_number
  project_number="$(cfg gcp.project_number)"
  local pool_id
  pool_id="$(cfg gcp.wif.pool_id)"
  local provider_id
  provider_id="$(cfg gcp.wif.provider_id)"
  local ca_crt="${REPO_ROOT}/Vault/pki/ca.crt"

  if $DRY_RUN; then
    echo "  [dry-run] Would create WIF pool, provider, and grant permissions"
    return
  fi

  echo ""
  echo "  This phase requires gcloud authentication."
  echo "  Run: gcloud auth login"
  echo "  Then: gcloud config set project $project_id"
  echo ""
  read -rp "  Press Enter when gcloud is authenticated (or 's' to skip): " choice
  if [[ "$choice" == "s" ]]; then
    warn "GCP WIF setup skipped"
    return
  fi

  # Create WIF pool (idempotent)
  log "  Creating WIF pool: $pool_id"
  gcloud iam workload-identity-pools create "$pool_id" \
    --project="$project_id" \
    --location=global \
    --display-name="Shinbee Pi X.509 Pool" 2>/dev/null || true
  ok "WIF pool created/exists"

  # Preprocess CA cert for trust store
  local ca_pem
  ca_pem=$(cat "$ca_crt" | sed 's/^[ ]*//g' | sed -z '$ s/\n$//' | tr '\n' '$' | sed 's/\$/\\n/g')

  # Create WIF provider (idempotent)
  log "  Creating WIF provider: $provider_id"
  gcloud iam workload-identity-pools providers create-x509 "$provider_id" \
    --project="$project_id" \
    --location=global \
    --workload-identity-pool="$pool_id" \
    --trust-store="trust_domain=googleapis.com,type=TRUST_ANCHOR,pem_certificate=${ca_pem}" \
    --attribute-mapping="google.subject=assertion.subject.dn.cn" 2>/dev/null || true
  ok "WIF provider created/exists"

  # Grant GCS access for backup
  local sa_member="principalSet://iam.googleapis.com/projects/${project_number}/locations/global/workloadIdentityPools/${pool_id}/*"
  log "  Granting GCS access for backup bucket..."
  gcloud storage buckets add-iam-policy-binding \
    "gs://$(cfg gcp.backup_bucket)" \
    --member="$sa_member" \
    --role="roles/storage.objectAdmin" 2>/dev/null || true
  ok "GCS backup bucket permissions granted"
}

# =============================================================================
# PHASE 10: aws_roles
# =============================================================================
phase_aws_roles() {
  log "Phase 10: AWS Roles Anywhere"

  # Install aws_signing_helper if missing
  if ! command -v aws_signing_helper &>/dev/null; then
    log "  Installing aws_signing_helper..."
    if ! $DRY_RUN; then
      local helper_url="https://rolesanywhere.amazonaws.com/releases/1.7.3/X86_64/Linux/aws_signing_helper"
      # ARM64 build
      helper_url="https://rolesanywhere.amazonaws.com/releases/1.7.3/AARCH64/Linux/aws_signing_helper"
      curl -fsSL "$helper_url" -o /tmp/aws_signing_helper
      sudo install -m 0755 /tmp/aws_signing_helper /usr/local/bin/aws_signing_helper
      rm -f /tmp/aws_signing_helper
    fi
    ok "aws_signing_helper installed"
  else
    ok "aws_signing_helper already installed"
  fi

  # Verify certificate_config.json exists
  local cert_config="${REPO_ROOT}/Vault/pki/certificate_config.json"
  if [[ -f "$cert_config" ]]; then
    ok "AWS certificate_config.json exists"
  else
    warn "AWS certificate_config.json missing — run pki phase first"
  fi
}

# =============================================================================
# PHASE 11: render
# =============================================================================
phase_render() {
  log "Phase 11: Render downstream config files"

  if $DRY_RUN; then
    echo "  [dry-run] Would generate all downstream config files from config.yaml"
    echo "  Files:"
    echo "    - Vault/vault.hcl"
    echo "    - Vault/docker-compose.yml"
    echo "    - Vault/pki/wif-credential-config.json"
    echo "    - Vault/pki/certificate_config.json"
    echo "    - services/fax/.env"
    echo "    - services/fax/config.yaml"
    echo "    - services/fax/mail2fax/config.yaml"
    echo "    - services/fax/terraform.tfvars"
    echo "    - services/inventory/shinbee-deploy/.env"
    echo "    - services/inventory/shinbee-deploy/config.yaml"
    return
  fi

  # Use Python to render all downstream files from config.yaml
  python3 << 'RENDEREOF'
import yaml, os, json

with open(os.environ.get("CONFIG_FILE", "config.yaml")) as f:
    C = yaml.safe_load(f)

REPO = C["global"]["repo_root"]
TZ = C["global"]["timezone"]
USER = C["global"]["user"]


def write_file(path, content, mode=0o644, owner=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    os.chmod(path, mode)
    if owner:
        import pwd, grp
        uid = pwd.getpwnam(owner).pw_uid
        gid = grp.getgrnam(owner).gr_gid
        os.chown(path, uid, gid)
    print(f"  \033[1;32m✓\033[0m {path}")


# -------------------------------------------------------------------------
# services/fax/.env (non-secret placeholders — render scripts fill secrets)
# -------------------------------------------------------------------------
fax = C["fax"]
write_file(
    f"{REPO}/services/fax/.env",
    f"""# RasPBX Docker Environment
# Auto-rendered from config.yaml — secrets injected by vault-render-fax.service

# MariaDB
MYSQL_ROOT_PASSWORD=VAULT_MANAGED
MYSQL_DATABASE={fax['db']['name']}
MYSQL_USER={fax['db']['user']}
MYSQL_PASSWORD=VAULT_MANAGED

# Asterisk AMI
AMI_USERNAME={fax['ami']['username']}
AMI_SECRET=VAULT_MANAGED

# Fax API
FAX_API_KEY=VAULT_MANAGED

# Timezone
TZ={TZ}
""",
    mode=0o600,
    owner=USER,
)

# -------------------------------------------------------------------------
# services/fax/config.yaml
# -------------------------------------------------------------------------
fax_config = {
    "expected_sip_server": fax["ntt"]["sip_server"],
    "fax": {
        "spool_directory": "/var/spool/asterisk/fax/",
    },
    "inventree": {
        "api_token": "",
        "upload_to": "purchase_order",
        "url": "",
    },
    "network": {
        "gateway_ip": fax["ntt"]["gateway_ip"],
        "interface": fax["ntt"]["interface"],
    },
    "retry": {
        "max_retries": fax["retry"]["max_retries"],
        "retry_interval_mins": fax["retry"]["interval_mins"],
    },
    "sip": {
        "allow": fax["sip"]["allow"],
        "domain": fax["ntt"]["sip_domain"],
        "from_user": str(fax["ntt"]["voice_did"]),
        "supported": fax["sip"]["supported"],
        "user_agent": "",
    },
}
content = yaml.dump(fax_config, default_flow_style=False, allow_unicode=True)
write_file(f"{REPO}/services/fax/config.yaml", content, mode=0o600, owner=USER)

# -------------------------------------------------------------------------
# services/fax/mail2fax/config.yaml
# -------------------------------------------------------------------------
mail2fax_config = {
    "aws": {
        "hosted_zone_id": C["aws"]["route53_zone_id"],
    },
    "certbot": {
        "email": fax["mail2fax"]["certbot_email"],
    },
    "domain": fax["mail2fax"]["domain"],
    "fax_api": {
        "api_key": "VAULT_MANAGED",
        "endpoint": f"http://host.docker.internal:{fax['faxapi']['port']}/send_fax",
    },
}
content = yaml.dump(mail2fax_config, default_flow_style=False, allow_unicode=True)
write_file(
    f"{REPO}/services/fax/mail2fax/config.yaml", content, mode=0o600, owner=USER
)

# -------------------------------------------------------------------------
# services/fax/terraform.tfvars
# -------------------------------------------------------------------------
tf = fax["terraform"]
tf_content = f"""# Auto-rendered from config.yaml — do not edit manually
project_id = "{C['gcp']['project_id']}"

region = "{C['gcp']['region']}"

drive_folder_id_original = "{tf['drive_folder_id_original']}"
drive_folder_id_work = "{tf['drive_folder_id_work']}"

notification_email_sender   = "{tf['notification_email_sender']}"
notification_email_receiver = "{tf['notification_email_receiver']}"

apps_script_url = "{tf['apps_script_url']}"
"""
write_file(f"{REPO}/services/fax/terraform.tfvars", tf_content, mode=0o644, owner=USER)

# -------------------------------------------------------------------------
# services/inventory/shinbee-deploy/.env
# -------------------------------------------------------------------------
inv = C["inventree"]
inv_env = f"""# InvenTree deployment configuration
# Auto-rendered from config.yaml — passwords via Docker secrets.

INVENTREE_TAG={inv['tag']}

# Domain name (used by nginx + certbot)
INVENTREE_DOMAIN={inv['domain']}

# Certbot notification email
CERTBOT_EMAIL={inv['certbot_email']}

# DNS mode: "production" = external IPs (A + AAAA), "test" = internal IPv4 only
DNS_MODE=production

# Route53 hosted zone ID (skips auto-detection if set)
ROUTE53_ZONE_ID={C['aws']['route53_zone_id']}

# Site URL (used by Django's ALLOWED_HOSTS / CSRF)
INVENTREE_SITE_URL={inv['site_url']}

# Exposed ports on the host
INVENTREE_WEB_PORT={inv['ports']['http']}
INVENTREE_HTTPS_PORT={inv['ports']['https']}

# Database name and user
INVENTREE_DB_ENGINE={inv['db']['engine']}
INVENTREE_DB_NAME={inv['db']['name']}
INVENTREE_DB_USER={inv['db']['user']}

# Background workers
INVENTREE_BACKGROUND_WORKERS={inv['background_workers']}

# Debug mode (set to True for development only)
INVENTREE_DEBUG={'True' if inv['debug'] else 'False'}

# Plugins (enabled for future ecommerce integration)
INVENTREE_PLUGINS_ENABLED={'true' if inv['plugins']['enabled'] else 'false'}
INVENTREE_PLUGIN_DIR={inv['plugins']['dir']}

# Google OAuth2
INVENTREE_SOCIAL_BACKENDS={inv['plugins']['social_backends']}
"""
write_file(
    f"{REPO}/services/inventory/shinbee-deploy/.env", inv_env, mode=0o644, owner=USER
)

# -------------------------------------------------------------------------
# services/inventory/shinbee-deploy/config.yaml
# -------------------------------------------------------------------------
inv_config = {
    "database": {
        "ENGINE": inv["db"]["engine"],
        "NAME": inv["db"]["name"],
        "USER": inv["db"]["user"],
        "HOST": "",
        "PORT": "",
        "OPTIONS": {
            "unix_socket": "/var/run/mysqld/mysqld.sock",
            "charset": "utf8mb4",
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        },
    },
    "plugins_enabled": inv["plugins"]["enabled"],
    "plugin_dir": inv["plugins"]["dir"],
    "social_providers": {
        "google": {
            "SCOPE": ["profile", "email"],
            "AUTH_PARAMS": {
                "access_type": "online",
                "hd": inv["oauth"]["hosted_domain"],
            },
            "APP": {
                "client_id": "REPLACE_WITH_GOOGLE_CLIENT_ID",
                "secret": "REPLACE_WITH_GOOGLE_CLIENT_SECRET",
            },
        }
    },
}
header = """# InvenTree configuration file (auto-rendered from config.yaml)
# PASSWORD is intentionally omitted — injected via Docker secret / env var.
# HOST is empty string so Django uses the unix_socket option.

"""
content = header + yaml.dump(inv_config, default_flow_style=False, allow_unicode=True)
write_file(
    f"{REPO}/services/inventory/shinbee-deploy/config.yaml", content, mode=0o644, owner=USER
)

print("\n  Render phase complete. Run vault-render scripts to inject secrets.")
RENDEREOF

  export CONFIG_FILE
  ok "All downstream config files rendered"

  # Now run the vault render scripts to inject actual secrets
  log "  Running vault-render scripts to inject secrets..."
  if sudo test -f "$(cfg vault.approle.fax.role_id_path)"; then
    run sudo bash "${REPO_ROOT}/Vault/scripts/render-fax-env.sh"
    ok "Fax secrets injected"
  else
    warn "Fax AppRole credentials not found — skipping secret injection"
  fi

  if sudo test -f "$(cfg vault.approle.inventree.role_id_path)"; then
    run sudo bash "${REPO_ROOT}/Vault/scripts/render-inventree-env.sh"
    ok "InvenTree secrets injected"
  else
    warn "InvenTree AppRole credentials not found — skipping secret injection"
  fi
}

# =============================================================================
# PHASE 12: systemd
# =============================================================================
phase_systemd() {
  log "Phase 12: systemd unit installation"

  # Remove legacy host-level services (now containerized or replaced)
  local legacy_units=("hfaxd.service" "faxq.service" "faxgetty@.service" "ngn-fax-api.service" "hylafax.service")
  for unit in "${legacy_units[@]}"; do
    if systemctl list-unit-files "$unit" &>/dev/null; then
      sudo systemctl disable --now "$unit" 2>/dev/null || true
      ok "Disabled legacy: $unit"
    fi
  done

  local vault_render_fax="/etc/systemd/system/vault-render-fax.service"
  local vault_render_inv="/etc/systemd/system/vault-render-inventree.service"
  local shinbee_backup_svc="/etc/systemd/system/shinbee-backup.service"
  local shinbee_backup_timer="/etc/systemd/system/shinbee-backup.timer"
  if $DRY_RUN; then
    echo "  [dry-run] Would install systemd units"
    return
  fi

  # vault-render-fax.service
  sudo tee "$vault_render_fax" > /dev/null << EOF
[Unit]
Description=Render fax service secrets from Vault
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
ExecStart=${REPO_ROOT}/Vault/scripts/render-fax-env.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
  ok "vault-render-fax.service"

  # vault-render-inventree.service
  sudo tee "$vault_render_inv" > /dev/null << EOF
[Unit]
Description=Render inventree secrets from Vault
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
ExecStart=${REPO_ROOT}/Vault/scripts/render-inventree-env.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
  ok "vault-render-inventree.service"

  # shinbee-backup.service (replaces vault-backup)
  # Remove old vault-backup units if present
  if [[ -f /etc/systemd/system/vault-backup.timer ]]; then
    sudo systemctl disable --now vault-backup.timer 2>/dev/null || true
    sudo rm -f /etc/systemd/system/vault-backup.service /etc/systemd/system/vault-backup.timer
    ok "Removed old vault-backup units"
  fi

  sudo tee "$shinbee_backup_svc" > /dev/null << EOF
[Unit]
Description=SHINBEE fax stack backup to GCS (K8s DBs backed up by CronJob)
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
ExecStart=${REPO_ROOT}/scripts/backup.sh
User=root

StandardOutput=journal
StandardError=journal
SyslogIdentifier=shinbee-backup
EOF
  ok "shinbee-backup.service"

  # shinbee-backup.timer
  sudo tee "$shinbee_backup_timer" > /dev/null << EOF
[Unit]
Description=Daily SHINBEE backup

[Timer]
OnCalendar=*-*-* 03:00:00
RandomizedDelaySec=300
Persistent=true

[Install]
WantedBy=timers.target
EOF
  ok "shinbee-backup.timer"

  # shinbee-fax.service (Docker Compose stack)
  local shinbee_fax_svc="/etc/systemd/system/shinbee-fax.service"
  sudo tee "$shinbee_fax_svc" > /dev/null << EOF
[Unit]
Description=SHINBEE Fax Docker Compose Stack
After=docker.service vault-render-fax.service
Requires=docker.service
Wants=vault-render-fax.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=${REPO_ROOT}/services/fax
ExecStart=/usr/bin/docker compose up -d --remove-orphans
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=300
TimeoutStopSec=120

[Install]
WantedBy=multi-user.target
EOF
  ok "shinbee-fax.service"

  # shinbee-inventree.service (Docker Compose stack)
  local shinbee_inv_svc="/etc/systemd/system/shinbee-inventree.service"
  sudo tee "$shinbee_inv_svc" > /dev/null << EOF
[Unit]
Description=SHINBEE InvenTree Docker Compose Stack
After=docker.service vault-render-inventree.service
Requires=docker.service
Wants=vault-render-inventree.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=${REPO_ROOT}/services/inventory/shinbee-deploy
ExecStart=/usr/bin/docker compose up -d --remove-orphans
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=300
TimeoutStopSec=120

[Install]
WantedBy=multi-user.target
EOF
  ok "shinbee-inventree.service"

  # shinbee-rakuten@.service (template unit for recon/renew modes)
  local shinbee_rakuten_svc="/etc/systemd/system/shinbee-rakuten@.service"
  sudo tee "$shinbee_rakuten_svc" > /dev/null << EOF
[Unit]
Description=SHINBEE Rakuten Agent (%i mode)
After=docker.service vault.service
Requires=docker.service

[Service]
Type=oneshot
WorkingDirectory=${REPO_ROOT}/services/rakuten-renewal
ExecStart=/usr/bin/docker compose run --rm agent python -m agent.main --mode %i
ExecStartPost=${REPO_ROOT}/services/rakuten-renewal/post-recon.sh
TimeoutStartSec=3600
StandardOutput=journal
StandardError=journal
EOF
  ok "shinbee-rakuten@.service"

  # shinbee-rakuten-recon.timer
  local shinbee_rakuten_recon_timer="/etc/systemd/system/shinbee-rakuten-recon.timer"
  sudo tee "$shinbee_rakuten_recon_timer" > /dev/null << 'EOF'
[Unit]
Description=SHINBEE Rakuten Recon Timer (Gemini-scheduled)

[Timer]
OnBootSec=15min
OnUnitActiveSec=7d
Persistent=true

[Install]
WantedBy=timers.target
EOF
  ok "shinbee-rakuten-recon.timer"

  # shinbee-rakuten-renew.timer
  local shinbee_rakuten_renew_timer="/etc/systemd/system/shinbee-rakuten-renew.timer"
  sudo tee "$shinbee_rakuten_renew_timer" > /dev/null << 'EOF'
[Unit]
Description=SHINBEE Rakuten Renewal Timer (every 80 days)

[Timer]
OnBootSec=15min
OnUnitActiveSec=80d
Persistent=true

[Install]
WantedBy=timers.target
EOF
  ok "shinbee-rakuten-renew.timer"

  # shinbee-daemon.service (Browser Daemon)
  local shinbee_daemon_svc="/etc/systemd/system/shinbee-daemon.service"
  sudo tee "$shinbee_daemon_svc" > /dev/null << EOF
[Unit]
Description=SHINBEE Browser Daemon
After=docker.service vault.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=${REPO_ROOT}/services/selenium-daemon
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=300
TimeoutStopSec=60

[Install]
WantedBy=multi-user.target
EOF
  ok "shinbee-daemon.service"

  # Reload and enable
  run sudo systemctl daemon-reload
  run sudo systemctl enable vault-render-fax.service
  run sudo systemctl enable vault-render-inventree.service
  run sudo systemctl enable shinbee-backup.timer
  run sudo systemctl enable shinbee-fax.service
  run sudo systemctl enable shinbee-inventree.service
  run sudo systemctl enable shinbee-rakuten-recon.timer
  run sudo systemctl enable shinbee-rakuten-renew.timer
  run sudo systemctl enable shinbee-daemon.service
  ok "All units enabled"
}

# =============================================================================
# PHASE 13: stacks
# =============================================================================
phase_stacks() {
  log "Phase 13: Docker stacks (via systemd)"

  # Start fax stack
  log "  Starting fax stack..."
  run sudo systemctl start shinbee-fax.service
  ok "Fax stack started"

  # Start inventree stack
  log "  Starting InvenTree stack..."
  run sudo systemctl start shinbee-inventree.service
  ok "InvenTree stack started"
}

# =============================================================================
# PHASE 14: firewall
# =============================================================================
phase_firewall() {
  log "Phase 15: Firewall (iptables)"

  if $DRY_RUN; then
    echo "  [dry-run] Would configure iptables rules"
    return
  fi

  local sip_server
  sip_server="$(cfg fax.ntt.sip_server)"
  local gateway_ip
  gateway_ip="$(cfg fax.ntt.gateway_ip)"
  local interface
  interface="$(cfg fax.ntt.interface)"

  # Flush existing rules for the interface
  sudo iptables -F INPUT 2>/dev/null || true

  # Allow loopback
  sudo iptables -A INPUT -i lo -j ACCEPT

  # Allow established connections
  sudo iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT

  # Allow SSH from any interface
  sudo iptables -A INPUT -p tcp --dport 22 -j ACCEPT

  # NTT SIP (UDP 5060) — only from SIP server on eth1
  sudo iptables -A INPUT -i "$interface" -p udp --dport 5060 -s "$sip_server" -j ACCEPT

  # NTT RTP (UDP 10000-20000) — from SIP server on eth1
  sudo iptables -A INPUT -i "$interface" -p udp --dport 10000:20000 -s "$sip_server" -j ACCEPT

  # Allow Docker bridge traffic
  sudo iptables -A INPUT -i docker0 -j ACCEPT
  sudo iptables -A INPUT -i br- -j ACCEPT

  # Allow Vault (localhost only — already bound to 127.0.0.1)
  sudo iptables -A INPUT -i lo -p tcp --dport "$(cfg vault.port)" -j ACCEPT

  # HTTP/HTTPS for InvenTree
  sudo iptables -A INPUT -p tcp --dport "$(cfg inventree.ports.http)" -j ACCEPT
  sudo iptables -A INPUT -p tcp --dport "$(cfg inventree.ports.https)" -j ACCEPT

  # SMTP for mail2fax
  sudo iptables -A INPUT -p tcp --dport 25 -j ACCEPT

  # Drop everything else on eth1 (NTT interface)
  sudo iptables -A INPUT -i "$interface" -j DROP

  ok "iptables rules applied"

  # Persist
  run sudo netfilter-persistent save
  ok "iptables rules persisted"
}

# =============================================================================
# PHASE: daemon
# =============================================================================
phase_daemon() {
  log "Phase: Browser daemon deployment"

  local daemon_dir="${REPO_ROOT}/services/selenium-daemon"

  # Build Docker image
  log "  Building daemon image..."
  run sg docker -c "docker compose -f ${daemon_dir}/docker-compose.yml build"
  ok "Daemon image built"
}

# =============================================================================
# Phase: Flutter dashboard
# =============================================================================
phase_flutter() {
  log "Phase: Flutter dashboard (build + deploy)"

  local KUBECONFIG="/etc/rancher/k3s/k3s.yaml"
  local NAMESPACE
  NAMESPACE=$(cfg flutter.namespace)
  local MANIFESTS="${REPO_ROOT}/infrastructure/kubernetes/manifests/flutter-dashboard"

  # 1. Build Flutter web app via K8s Job
  log "  Building Flutter web app..."
  if [[ -x "${REPO_ROOT}/infrastructure/kubernetes/scripts/flutter-build.sh" ]]; then
    run sudo "${REPO_ROOT}/infrastructure/kubernetes/scripts/flutter-build.sh" "${REPO_ROOT}" master web
    ok "Flutter web build submitted"
  else
    warn "flutter-build.sh not found or not executable, skipping build"
  fi

  # 2. Apply K8s manifests (configmap, deployment, service, ingress)
  log "  Applying flutter-dashboard manifests..."
  for f in configmap-nginx.yaml deployment.yaml service.yaml ingress.yaml; do
    if [[ -f "${MANIFESTS}/${f}" ]]; then
      run sudo KUBECONFIG="$KUBECONFIG" kubectl apply -f "${MANIFESTS}/${f}"
      ok "Applied ${f}"
    fi
  done

  # 3. Deploy latest build (rollout restart triggers init container to fetch from GCS)
  log "  Deploying latest Flutter build..."
  if [[ -x "${REPO_ROOT}/infrastructure/kubernetes/scripts/flutter-deploy-web.sh" ]]; then
    run sudo "${REPO_ROOT}/infrastructure/kubernetes/scripts/flutter-deploy-web.sh"
    ok "Flutter dashboard deployed"
  else
    run sudo KUBECONFIG="$KUBECONFIG" kubectl -n "$NAMESPACE" rollout restart deployment/flutter-dashboard
    ok "Flutter dashboard rollout restarted"
  fi

  ok "Flutter dashboard phase complete"
}

# =============================================================================
# Phase: AI Assistant
# =============================================================================
phase_ai_assistant() {
  log "Phase: AI Assistant (build + deploy)"

  local KUBECONFIG="/etc/rancher/k3s/k3s.yaml"
  local NAMESPACE
  NAMESPACE=$(cfg ai_assistant.namespace)
  local MANIFESTS="${REPO_ROOT}/infrastructure/kubernetes/manifests/ai-assistant"
  local REGISTRY="asia-northeast1-docker.pkg.dev/$(cfg gcp.project)/shinbee"
  local IMAGE="${REGISTRY}/ai-assistant:latest"

  # 1. Build Docker image via Cloud Build
  log "  Building AI assistant image via Cloud Build..."
  if [[ -x "${REPO_ROOT}/infrastructure/kubernetes/scripts/cloud-build.sh" ]]; then
    run "${REPO_ROOT}/infrastructure/kubernetes/scripts/cloud-build.sh" \
      "${REPO_ROOT}/services/ai-assistant" "$IMAGE"
    ok "AI assistant image built"
  else
    log "  Building directly with gcloud..."
    run gcloud builds submit "${REPO_ROOT}/services/ai-assistant" \
      --tag="$IMAGE" --project="$(cfg gcp.project)" --quiet
    ok "AI assistant image built"
  fi

  # 2. Apply K8s manifests (deployment, service, cronjobs)
  log "  Applying ai-assistant manifests..."
  for f in deployment.yaml service.yaml cronjob.yaml cronjob-sop-sync.yaml; do
    if [[ -f "${MANIFESTS}/${f}" ]]; then
      run sudo KUBECONFIG="$KUBECONFIG" kubectl apply -f "${MANIFESTS}/${f}"
      ok "Applied ${f}"
    fi
  done

  # 3. Restart deployment to pick up latest image
  log "  Restarting ai-assistant deployment..."
  run sudo KUBECONFIG="$KUBECONFIG" kubectl -n "$NAMESPACE" \
    rollout restart deployment/ai-assistant
  ok "AI assistant deployment restarted"

  # 4. Wait for rollout
  log "  Waiting for rollout to complete..."
  run sudo KUBECONFIG="$KUBECONFIG" kubectl -n "$NAMESPACE" \
    rollout status deployment/ai-assistant --timeout=300s
  ok "AI assistant phase complete"
}

# =============================================================================
# Phase dispatcher
# =============================================================================
ALL_PHASES=(
  preflight packages docker pki vault_deploy vault_init
  vault_configure secrets gcp_wif aws_roles render
  systemd daemon stacks firewall
  flutter ai_assistant
)

if [[ -n "$PHASE" ]]; then
  # Run single phase
  func="phase_${PHASE}"
  if declare -f "$func" &>/dev/null; then
    "$func"
  else
    die "Unknown phase: $PHASE (available: ${ALL_PHASES[*]})"
  fi
else
  # Run all phases
  log "SHINBEE Unified Installer — running all phases"
  echo ""
  for p in "${ALL_PHASES[@]}"; do
    "phase_${p}"
    echo ""
  done
  log "Installation complete!"
fi
