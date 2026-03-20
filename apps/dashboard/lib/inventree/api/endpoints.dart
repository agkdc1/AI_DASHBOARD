class InvenTreeEndpoints {
  static const base = '/api';
  static const parts = '$base/part/';
  static const partCategories = '$base/part/category/';
  static const stock = '$base/stock/';
  static const stockLocations = '$base/stock/location/';
  static const stockTrack = '$base/stock/track/';
  static const companies = '$base/company/';
  static const supplierParts = '$base/company/part/';
  static const purchaseOrders = '$base/order/po/';
  static const purchaseOrderLines = '$base/order/po/line/';
  static const salesOrders = '$base/order/so/';
  static const salesOrderLines = '$base/order/so/line/';
  static const salesOrderAllocations = '$base/order/so/allocation/';
  static const salesOrderShipments = '$base/order/so/shipment/';
  static const barcodeScan = '$base/barcode/';
  static const bom = '$base/bom/';
  static const attachments = '$base/attachment/';
  static const notifications = '$base/notifications/';
  static const userMe = '$base/user/me/';
  static const search = '$base/search/';

  // Plugin endpoints
  static const waybillGenerate = '/plugin/invoice_print/generate';
  static const waybillPdf = '/plugin/invoice_print/pdf';
}
