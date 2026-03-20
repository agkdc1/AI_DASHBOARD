"""Integration tests for Vikunja REST API.

Run with: RUN_INTEGRATION=1 pytest -m integration tests/integration/test_vikunja_api.py -v
"""

import pytest

pytestmark = [pytest.mark.integration]


class TestVikunjaAPI:
    def test_health_check(self, vikunja_client):
        resp = vikunja_client.get("/api/v1/info")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data

    def test_create_project(self, vikunja_client, vikunja_cleanup):
        resp = vikunja_client.put("/api/v1/projects", json={
            "title": "TEST-PROJECT",
        })
        assert resp.status_code in (200, 201)
        project = resp.json()
        vikunja_cleanup["projects"].append(project["id"])
        assert project["title"] == "TEST-PROJECT"

    def test_create_task(self, vikunja_client, vikunja_cleanup):
        # Create project first
        resp = vikunja_client.put("/api/v1/projects", json={
            "title": "TEST-TASK-PROJECT",
        })
        project_id = resp.json()["id"]
        vikunja_cleanup["projects"].append(project_id)

        # Create task
        resp = vikunja_client.put(f"/api/v1/projects/{project_id}/tasks", json={
            "title": "TEST-TASK",
            "priority": 2,
        })
        assert resp.status_code in (200, 201)
        task = resp.json()
        vikunja_cleanup["tasks"].append(task["id"])
        assert task["title"] == "TEST-TASK"
        assert task["priority"] == 2

    def test_search_tasks(self, vikunja_client, vikunja_cleanup):
        # Create project + task
        resp = vikunja_client.put("/api/v1/projects", json={"title": "TEST-SEARCH-PROJ"})
        project_id = resp.json()["id"]
        vikunja_cleanup["projects"].append(project_id)

        resp = vikunja_client.put(f"/api/v1/projects/{project_id}/tasks", json={
            "title": "UNIQUE-SEARCH-TOKEN-12345",
        })
        task_id = resp.json()["id"]
        vikunja_cleanup["tasks"].append(task_id)

        # Search
        resp = vikunja_client.get("/api/v1/tasks/all", params={
            "s": "UNIQUE-SEARCH-TOKEN-12345",
        })
        assert resp.status_code == 200
        tasks = resp.json()
        assert any(t["id"] == task_id for t in tasks)

    def test_update_task(self, vikunja_client, vikunja_cleanup):
        resp = vikunja_client.put("/api/v1/projects", json={"title": "TEST-UPD-PROJ"})
        project_id = resp.json()["id"]
        vikunja_cleanup["projects"].append(project_id)

        resp = vikunja_client.put(f"/api/v1/projects/{project_id}/tasks", json={
            "title": "TEST-UPDATE-TASK",
        })
        task_id = resp.json()["id"]
        vikunja_cleanup["tasks"].append(task_id)

        # Mark done
        resp = vikunja_client.post(f"/api/v1/tasks/{task_id}", json={"done": True})
        assert resp.status_code == 200
        assert resp.json()["done"] is True

    def test_delete_task(self, vikunja_client, vikunja_cleanup):
        resp = vikunja_client.put("/api/v1/projects", json={"title": "TEST-DEL-PROJ"})
        project_id = resp.json()["id"]
        vikunja_cleanup["projects"].append(project_id)

        resp = vikunja_client.put(f"/api/v1/projects/{project_id}/tasks", json={
            "title": "TEST-DELETE-TASK",
        })
        task_id = resp.json()["id"]
        # Delete directly (don't add to cleanup)
        resp = vikunja_client.delete(f"/api/v1/tasks/{task_id}")
        assert resp.status_code in (200, 204)

    def test_delete_project(self, vikunja_client):
        resp = vikunja_client.put("/api/v1/projects", json={"title": "TEST-DEL-PROJ2"})
        project_id = resp.json()["id"]
        resp = vikunja_client.delete(f"/api/v1/projects/{project_id}")
        assert resp.status_code in (200, 204)

    def test_list_projects(self, vikunja_client):
        resp = vikunja_client.get("/api/v1/projects")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
