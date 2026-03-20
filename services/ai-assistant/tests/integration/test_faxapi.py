"""Integration tests for faxapi (Asterisk extension management via SQLite + confgen).

Run with: RUN_INTEGRATION=1 pytest -m integration tests/integration/test_faxapi.py -v
"""

import pytest

pytestmark = [pytest.mark.integration]


class TestFaxAPI:
    def test_health_check(self, faxapi_client):
        resp = faxapi_client.get("/health")
        assert resp.status_code == 200

    def test_list_extensions(self, faxapi_client):
        resp = faxapi_client.get("/extensions")
        assert resp.status_code == 200
        assert isinstance(resp.json(), (list, dict))

    def test_create_extension(self, faxapi_client, faxapi_cleanup):
        resp = faxapi_client.post("/extensions", json={
            "extension": "399",
            "name": "TEST-EXT",
            "password": "testpass399",
        })
        assert resp.status_code in (200, 201)
        faxapi_cleanup["extensions"].append("399")

    def test_get_extension(self, faxapi_client, faxapi_cleanup):
        # Create first
        faxapi_client.post("/extensions", json={
            "extension": "398",
            "name": "TEST-GET",
            "password": "testpass398",
        })
        faxapi_cleanup["extensions"].append("398")

        resp = faxapi_client.get("/extensions/398")
        assert resp.status_code == 200

    def test_delete_extension(self, faxapi_client):
        # Create then delete
        faxapi_client.post("/extensions", json={
            "extension": "397",
            "name": "TEST-DEL",
            "password": "testpass397",
        })
        resp = faxapi_client.delete("/extensions/397")
        assert resp.status_code in (200, 204)

    def test_reload(self, faxapi_client):
        resp = faxapi_client.post("/extensions/reload")
        assert resp.status_code == 200

    def test_duplicate_extension(self, faxapi_client, faxapi_cleanup):
        faxapi_client.post("/extensions", json={
            "extension": "396",
            "name": "TEST-DUP",
            "password": "testpass396",
        })
        faxapi_cleanup["extensions"].append("396")

        # Try creating again
        resp = faxapi_client.post("/extensions", json={
            "extension": "396",
            "name": "TEST-DUP2",
            "password": "testpass396",
        })
        assert resp.status_code in (409, 400, 200)  # Depends on API behavior

    def test_nonexistent_extension(self, faxapi_client):
        resp = faxapi_client.get("/extensions/999")
        assert resp.status_code in (404, 400)
