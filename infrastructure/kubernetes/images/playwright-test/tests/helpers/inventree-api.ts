const TEST_API_URL = process.env.TEST_PORTAL_URL?.replace('test-portal', 'test-api') || 'https://test-api.your-domain.com';

/**
 * InvenTree API client for test setup and verification.
 */
export class InvenTreeApi {
  private baseUrl: string;
  private token: string;

  constructor(token: string, baseUrl?: string) {
    this.baseUrl = baseUrl || TEST_API_URL;
    this.token = token;
  }

  private async request(method: string, path: string, body?: any): Promise<any> {
    const resp = await fetch(`${this.baseUrl}${path}`, {
      method,
      headers: {
        Authorization: `Token ${this.token}`,
        'Content-Type': 'application/json',
      },
      body: body ? JSON.stringify(body) : undefined,
    });

    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(`API ${method} ${path} failed (${resp.status}): ${text}`);
    }

    return resp.json();
  }

  async get(path: string): Promise<any> {
    return this.request('GET', path);
  }

  async post(path: string, data: any): Promise<any> {
    return this.request('POST', path, data);
  }

  async patch(path: string, data: any): Promise<any> {
    return this.request('PATCH', path, data);
  }

  // --- Convenience methods ---

  async listParts(): Promise<any[]> {
    const data = await this.get('/api/part/?limit=100');
    return data.results || data;
  }

  async listSalesOrders(): Promise<any[]> {
    const data = await this.get('/api/order/so/?limit=100');
    return data.results || data;
  }

  async getSalesOrder(pk: number): Promise<any> {
    return this.get(`/api/order/so/${pk}/`);
  }

  async getSalesOrderLines(pk: number): Promise<any[]> {
    const data = await this.get(`/api/order/so-line/?order=${pk}&limit=100`);
    return data.results || data;
  }

  async listStockLocations(): Promise<any[]> {
    const data = await this.get('/api/stock/location/?limit=100');
    return data.results || data;
  }
}
