"""Quick login test for Yamato and Sagawa on-demand sessions."""

import asyncio
import os
import sys

os.environ.setdefault("CONFIG_PATH", "/home/pi/SHINBEE/config.yaml")
os.environ.setdefault("VAULT_ADDR", "http://127.0.0.1:8200")
os.environ.setdefault(
    "VAULT_APPROLE_ROLE_ID_PATH", "/root/vault-approle-admin-role-id"
)
os.environ.setdefault(
    "VAULT_APPROLE_SECRET_ID_PATH", "/root/vault-approle-admin-secret-id"
)

from daemon.vault_client import VaultClient
from daemon.sessions.yamato import YamatoSession
from daemon.sessions.sagawa import SagawaSession


async def test_session(name, session):
    print(f"\n{'='*60}")
    print(f"Testing {name} login")
    print(f"{'='*60}")

    try:
        print(f"[{name}] Acquiring browser...")
        await session.acquire_browser()
        print(f"[{name}] Browser acquired, is_logged_in={session.is_logged_in}")

        if not session.is_logged_in:
            print(f"[{name}] Attempting login...")
            success = await session.login()
            print(f"[{name}] Login result: {success}")
        else:
            print(f"[{name}] Already logged in from cookies")

        print(f"[{name}] Checking is_alive...")
        alive = await session.is_alive()
        print(f"[{name}] is_alive: {alive}")

    except Exception as e:
        print(f"[{name}] ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
    finally:
        print(f"[{name}] Releasing browser...")
        await session.release_browser()
        print(f"[{name}] Done")


async def main():
    vault = VaultClient()

    carrier = sys.argv[1] if len(sys.argv) > 1 else "both"

    if carrier in ("yamato", "both"):
        session = YamatoSession(vault_client=vault)
        await test_session("yamato", session)

    if carrier in ("sagawa", "both"):
        session = SagawaSession(vault_client=vault)
        await test_session("sagawa", session)


if __name__ == "__main__":
    asyncio.run(main())
