### Role: Senior Python Developer & InvenTree Expert
### Task: Build 'InvenTree-MultiChannel-Plugin'

Now, create a comprehensive plan in PLAN.md and implement the plugin following these strict technical requirements. Use InvenTree native Mixins (IntegrationPlugin, SettingsMixin, ScheduleMixin).

#### 0. Golden Rules
- Read RULE.md and remember it.
- Copy the content of RULE.md to PLAN.md

#### 1. Directory Structure
- `ecommerce_plugin.py`: Main entry point (Plugin Class).
- `schema.py`: Unified Pydantic models for Order and Item.
- `providers/`: Directory containing `base.py`, `amazon.py`, `rakuten.py`, `yahoo.py`, `qoo10.py`.

#### 2. Key Implementations
- **Auth**:
  - Amazon: SP-API (LWA + SigV4).
  - Rakuten: RMS 2.0 (ESA Auth: Base64 ServiceSecret:LicenseKey).
  - Yahoo: OAuth2 (Client ID/Secret + Refresh Token flow).
  - Qoo10: API Key + SellerAuthKey.
- **Unified Schema**: Define `UnifiedOrder` with fields: `platform`, `order_id`, `status` (created, marked, sent, cancelled), `customer_name`, `address`, `items` (sku, qty, price), `tracking_no`.
- **Status Mapping**:
  - Amazon: {Unshipped: marked, Shipped: sent, Canceled: cancelled}
  - Rakuten: {100-300: marked, 400: sent, 900: cancelled}
  - Yahoo: {1,3: marked, 4: sent, 9: cancelled}
  - Qoo10: {2,3: marked, 4: sent}

#### 3. InvenTree Integration
- Use `SettingsMixin` to store API credentials (masked) in the UI.
- Use `ScheduleMixin` to run `fetch_orders` and `sync_inventory` every 15 minutes.
- Implement logic to:
  1. Fetch from platforms -> Convert to `UnifiedOrder`.
  2. Check if `platform_order_id` exists in InvenTree SalesOrders (use a custom metadata field).
  3. Create `SalesOrder` & `SalesOrderLineItem`.
  4. Auto-allocate stock from 'Online Fulfillment' location.
  5. On InvenTree shipment, push `tracking_number` back to the respective platform API.

#### 4. Execution Flow
1. Write the full architectural plan to PLAN.md.
2. Define `schema.py` first.
3. Implement `providers/base.py` and `providers/amazon.py` as a priority.
4. Update PLAN.md as you complete each task.

Go.
