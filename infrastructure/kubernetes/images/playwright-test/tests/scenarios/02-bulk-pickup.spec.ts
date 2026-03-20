import { test, expect } from '@playwright/test';
import { getApiToken } from '../helpers/auth';
import { InvenTreeApi } from '../helpers/inventree-api';

test.describe('Scenario 2: Bulk Pickup and Send', () => {
  let api: InvenTreeApi;

  test.beforeAll(async () => {
    const token = await getApiToken();
    api = new InvenTreeApi(token);
  });

  test('2.1 Verify multi-customer orders exist (SO-0003, 0004, 0005)', async () => {
    const orders = await api.listSalesOrders();
    const refs = orders.map((o: any) => o.reference);
    expect(refs).toContain('SO-0003');
    expect(refs).toContain('SO-0004');
    expect(refs).toContain('SO-0005');
  });

  test('2.2 Verify bulk order line items', async () => {
    const orders = await api.listSalesOrders();

    // SO-0003 should have 3 items
    const so003 = orders.find((o: any) => o.reference === 'SO-0003');
    expect(so003).toBeTruthy();
    const lines003 = await api.getSalesOrderLines(so003.pk);
    expect(lines003.length).toBe(3);

    // SO-0004 should have 2 items
    const so004 = orders.find((o: any) => o.reference === 'SO-0004');
    expect(so004).toBeTruthy();
    const lines004 = await api.getSalesOrderLines(so004.pk);
    expect(lines004.length).toBe(2);

    // SO-0005 should have 3 items
    const so005 = orders.find((o: any) => o.reference === 'SO-0005');
    expect(so005).toBeTruthy();
    const lines005 = await api.getSalesOrderLines(so005.pk);
    expect(lines005.length).toBe(3);
  });

  test('2.3 Verify orders belong to different customers', async () => {
    const orders = await api.listSalesOrders();
    const so003 = orders.find((o: any) => o.reference === 'SO-0003');
    const so004 = orders.find((o: any) => o.reference === 'SO-0004');
    const so005 = orders.find((o: any) => o.reference === 'SO-0005');

    // SO-0003 and SO-0004 belong to same customer (ビューティーワールド大阪)
    expect(so003.customer).toBe(so004.customer);
    // SO-0005 belongs to different customer (韓国美容株式会社)
    expect(so005.customer).not.toBe(so003.customer);
  });

  test('2.4 Verify large order SO-0006 has 10 line items', async () => {
    const orders = await api.listSalesOrders();
    const so006 = orders.find((o: any) => o.reference === 'SO-0006');
    expect(so006).toBeTruthy();
    const lines = await api.getSalesOrderLines(so006.pk);
    expect(lines.length).toBe(10);
  });

  test('2.5 Verify stock quantities are sufficient for orders', async () => {
    // Check that there's enough stock for at least SO-0001
    const parts = await api.listParts();
    const skPart = parts.find((p: any) => p.IPN === 'SB-SK-001');
    expect(skPart).toBeTruthy();
    expect(skPart.in_stock).toBeGreaterThan(0);
  });
});
