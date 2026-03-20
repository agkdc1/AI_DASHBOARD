"""Integration tests for InvenTree REST API.

Creates real test data and cleans up after each test.
Run with: RUN_INTEGRATION=1 pytest -m integration tests/integration/test_inventree_api.py -v
"""

import pytest

pytestmark = [pytest.mark.integration]


class TestInvenTreeAPI:
    def test_health_check(self, inventree_client):
        resp = inventree_client.get("/api/")
        assert resp.status_code == 200
        data = resp.json()
        assert "server" in data or "version" in data

    def test_create_category(self, inventree_client, inventree_cleanup):
        resp = inventree_client.post("/api/part/category/", json={
            "name": "TEST-CATEGORY",
            "description": "Integration test category",
        })
        assert resp.status_code in (200, 201)
        cat = resp.json()
        inventree_cleanup["categories"].append(cat["pk"])
        assert cat["name"] == "TEST-CATEGORY"

    def test_create_part(self, inventree_client, inventree_cleanup):
        # Create category first
        resp = inventree_client.post("/api/part/category/", json={
            "name": "TEST-PART-CAT",
            "description": "For part creation test",
        })
        assert resp.status_code in (200, 201)
        cat_id = resp.json()["pk"]
        inventree_cleanup["categories"].append(cat_id)

        # Create part
        resp = inventree_client.post("/api/part/", json={
            "name": "TEST-001",
            "description": "Test part",
            "category": cat_id,
            "component": True,
        })
        assert resp.status_code in (200, 201)
        part = resp.json()
        inventree_cleanup["parts"].append(part["pk"])
        assert part["name"] == "TEST-001"

    def test_create_stock_location(self, inventree_client, inventree_cleanup):
        resp = inventree_client.post("/api/stock/location/", json={
            "name": "TEST-LOC",
        })
        assert resp.status_code in (200, 201)
        loc = resp.json()
        inventree_cleanup["stock_locations"].append(loc["pk"])
        assert loc["name"] == "TEST-LOC"

    def test_create_stock_item(self, inventree_client, inventree_cleanup):
        # Category → Part → Location → Stock Item
        resp = inventree_client.post("/api/part/category/", json={"name": "TEST-STOCK-CAT"})
        cat_id = resp.json()["pk"]
        inventree_cleanup["categories"].append(cat_id)

        resp = inventree_client.post("/api/part/", json={
            "name": "TEST-STOCK-PART", "category": cat_id, "component": True,
        })
        part_id = resp.json()["pk"]
        inventree_cleanup["parts"].append(part_id)

        resp = inventree_client.post("/api/stock/location/", json={"name": "TEST-STOCK-LOC"})
        loc_id = resp.json()["pk"]
        inventree_cleanup["stock_locations"].append(loc_id)

        resp = inventree_client.post("/api/stock/", json={
            "part": part_id, "location": loc_id, "quantity": 10,
        })
        assert resp.status_code in (200, 201)
        item = resp.json()
        inventree_cleanup["stock_items"].append(item["pk"])
        assert item["quantity"] == 10

    def test_create_company(self, inventree_client, inventree_cleanup):
        resp = inventree_client.post("/api/company/", json={
            "name": "TEST-CUSTOMER",
            "is_customer": True,
        })
        assert resp.status_code in (200, 201)
        company = resp.json()
        inventree_cleanup["companies"].append(company["pk"])
        assert company["name"] == "TEST-CUSTOMER"

    def test_create_sales_order(self, inventree_client, inventree_cleanup):
        # Company first
        resp = inventree_client.post("/api/company/", json={
            "name": "TEST-SO-CUSTOMER", "is_customer": True,
        })
        company_id = resp.json()["pk"]
        inventree_cleanup["companies"].append(company_id)

        resp = inventree_client.post("/api/order/so/", json={
            "customer": company_id,
            "description": "Test order",
        })
        assert resp.status_code in (200, 201)
        order = resp.json()
        inventree_cleanup["sales_orders"].append(order["pk"])

    def test_list_parts(self, inventree_client):
        resp = inventree_client.get("/api/part/", params={"limit": 5})
        assert resp.status_code == 200

    def test_update_part(self, inventree_client, inventree_cleanup):
        # Create a part
        resp = inventree_client.post("/api/part/category/", json={"name": "TEST-UPD-CAT"})
        cat_id = resp.json()["pk"]
        inventree_cleanup["categories"].append(cat_id)

        resp = inventree_client.post("/api/part/", json={
            "name": "TEST-UPDATE", "category": cat_id, "component": True,
        })
        part_id = resp.json()["pk"]
        inventree_cleanup["parts"].append(part_id)

        # Update
        resp = inventree_client.patch(f"/api/part/{part_id}/", json={
            "description": "Updated description",
        })
        assert resp.status_code == 200
        assert resp.json()["description"] == "Updated description"

    def test_delete_part(self, inventree_client, inventree_cleanup):
        resp = inventree_client.post("/api/part/category/", json={"name": "TEST-DEL-CAT"})
        cat_id = resp.json()["pk"]
        inventree_cleanup["categories"].append(cat_id)

        resp = inventree_client.post("/api/part/", json={
            "name": "TEST-DELETE", "category": cat_id, "component": True,
        })
        part_id = resp.json()["pk"]
        # Don't add to cleanup — we'll delete it manually
        resp = inventree_client.delete(f"/api/part/{part_id}/")
        assert resp.status_code in (200, 204)

    def test_get_part_detail(self, inventree_client, inventree_cleanup):
        resp = inventree_client.post("/api/part/category/", json={"name": "TEST-DET-CAT"})
        cat_id = resp.json()["pk"]
        inventree_cleanup["categories"].append(cat_id)

        resp = inventree_client.post("/api/part/", json={
            "name": "TEST-DETAIL", "category": cat_id, "component": True,
        })
        part_id = resp.json()["pk"]
        inventree_cleanup["parts"].append(part_id)

        resp = inventree_client.get(f"/api/part/{part_id}/")
        assert resp.status_code == 200
        assert resp.json()["name"] == "TEST-DETAIL"
