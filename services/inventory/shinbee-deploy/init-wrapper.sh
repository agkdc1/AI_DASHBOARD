#!/bin/bash
set -e

# Read MySQL password from Docker secret and export as env var.
# This is the only place the password is read — it never appears in
# config.yaml or .env files.
if [ -f /run/secrets/mysql_password ]; then
    export INVENTREE_DB_PASSWORD="$(cat /run/secrets/mysql_password)"
else
    echo "WARNING: /run/secrets/mysql_password not found"
fi

# Always refresh config.yaml from template so credential rotation takes effect.
# (Non-secret fields like DB, plugins, allowed_hosts are static in the template.)
cp /home/inventree/config.yaml.default "${INVENTREE_CONFIG_FILE}"

# Inject Google OAuth credentials from Docker secrets into config.yaml
if [ -f /run/secrets/google_client_id ] && [ -f /run/secrets/google_client_secret ]; then
    GOOGLE_CID="$(cat /run/secrets/google_client_id)"
    GOOGLE_SEC="$(cat /run/secrets/google_client_secret)"
    sed -i "s|REPLACE_WITH_GOOGLE_CLIENT_ID|${GOOGLE_CID}|g" "${INVENTREE_CONFIG_FILE}"
    sed -i "s|REPLACE_WITH_GOOGLE_CLIENT_SECRET|${GOOGLE_SEC}|g" "${INVENTREE_CONFIG_FILE}"
    echo "Google OAuth credentials injected into config"
else
    echo "WARNING: Google OAuth secret files not found — SSO may not work"
fi

# Inject cookie domain into Django settings for cross-subdomain session sharing
# (appending to settings.py — last assignment wins in Python)
if [ -n "${INVENTREE_COOKIE_DOMAIN:-}" ]; then
    SETTINGS_PY="/home/inventree/src/backend/InvenTree/InvenTree/settings.py"
    if ! grep -q 'SESSION_COOKIE_DOMAIN' "$SETTINGS_PY"; then
        cat >> "$SETTINGS_PY" << 'PYEOF'

# Shinbee: share cookies across subdomains (injected by init-wrapper.sh)
import os as _os
_cd = _os.environ.get('INVENTREE_COOKIE_DOMAIN')
if _cd:
    SESSION_COOKIE_DOMAIN = _cd
    CSRF_COOKIE_DOMAIN = _cd
PYEOF
    fi
    echo "Cookie domain set to ${INVENTREE_COOKIE_DOMAIN}"
fi

# ---------- Replicate essential init.sh setup ----------
# (We cannot source init.sh because it ends with exec "$@")

if command -v git &> /dev/null; then
    git config --global --add safe.directory /home/inventree 2>/dev/null || true
fi

mkdir -p "${INVENTREE_STATIC_ROOT}" "${INVENTREE_MEDIA_ROOT}" "${INVENTREE_BACKUP_DIR}"

if [ -f "${INVENTREE_CONFIG_FILE}" ]; then
    echo "Loading config file : ${INVENTREE_CONFIG_FILE}"
fi

# Activate Python venv if configured
if [[ -n "${INVENTREE_PY_ENV}" ]] && [[ -d "${INVENTREE_PY_ENV}" ]]; then
    echo "Using Python virtual environment: ${INVENTREE_PY_ENV}"
    source "${INVENTREE_PY_ENV}/bin/activate"
fi

cd "${INVENTREE_HOME}"

# ---------- Run database migrations + collect static ----------
# Only the server should run migrations/static. The worker (invoke worker)
# skips these to avoid MySQL lock contention on simultaneous startup.
if [ "$1" != "invoke" ]; then
    echo "Running database migrations..."
    invoke migrate
    echo "Collecting static files..."
    invoke static

    # Create SSO-only superuser if INVENTREE_ADMIN_EMAIL is set
    if [ -n "${INVENTREE_ADMIN_EMAIL:-}" ]; then
        ADMIN_USERNAME="${INVENTREE_ADMIN_EMAIL%%@*}"
        python "${INVENTREE_BACKEND_DIR:-/home/inventree/src/backend}/InvenTree/manage.py" shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(email='${INVENTREE_ADMIN_EMAIL}').exists():
    u = User.objects.create_superuser('${ADMIN_USERNAME}', '${INVENTREE_ADMIN_EMAIL}', None)
    u.set_unusable_password(); u.save()
    print(f'Created SSO-only superuser: ${ADMIN_USERNAME}')
else:
    print(f'Superuser already exists: ${INVENTREE_ADMIN_EMAIL}')
"
    fi
fi

# Start the requested command (uWSGI for server, invoke worker for worker)
exec "$@"
