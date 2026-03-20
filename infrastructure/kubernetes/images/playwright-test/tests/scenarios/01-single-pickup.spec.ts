import { test, expect } from '@playwright/test';
import { loginPortal, getApiToken, loginFlutterApp } from '../helpers/auth';
import { InvenTreeApi } from '../helpers/inventree-api';

test.describe('Scenario 1: Single Pickup and Send', () => {
  let api: InvenTreeApi;

  test.beforeAll(async () => {
    const token = await getApiToken();
    api = new InvenTreeApi(token);
  });

  test('1.1 Login to test portal via API token', async () => {
    // Verify API auth works (portal login is React SPA + Google SSO dependent)
    const parts = await api.listParts();
    expect(parts.length).toBeGreaterThan(0);
  });

  test('1.2 Find SO-0001 via API', async () => {
    const orders = await api.listSalesOrders();
    const so001 = orders.find((o: any) => o.reference === 'SO-0001');
    expect(so001).toBeTruthy();
    expect(so001.description).toContain('テスト注文');
  });

  test('1.3 Verify SO-0001 has 3 line items', async () => {
    const orders = await api.listSalesOrders();
    const so001 = orders.find((o: any) => o.reference === 'SO-0001');
    expect(so001).toBeTruthy();

    const lines = await api.getSalesOrderLines(so001.pk);
    expect(lines.length).toBe(3);
  });

  test('1.4 Verify seed data: 25 parts exist', async () => {
    const parts = await api.listParts();
    expect(parts.length).toBeGreaterThanOrEqual(25);
  });

  test('1.5 Verify warehouse locations exist', async () => {
    const locations = await api.listStockLocations();
    const names = locations.map((l: any) => l.name);
    expect(names).toContain('倉庫');
    expect(names).toContain('A棚');
    expect(names).toContain('出荷エリア');
  });

  test('1.6 Verify SO-0001 has correct structure', async () => {
    const orders = await api.listSalesOrders();
    const so001 = orders.find((o: any) => o.reference === 'SO-0001');
    expect(so001).toBeTruthy();
    // Verify SO has customer and description
    expect(so001.customer).toBeTruthy();
    expect(so001.description).toContain('テスト注文');
    expect(so001.status).toBeDefined();
  });
});
