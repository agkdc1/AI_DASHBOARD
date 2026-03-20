import 'package:flutter_test/flutter_test.dart';
import 'package:shinbee_dashboard/inventree/api/endpoints.dart';

void main() {
  group('InvenTree endpoints', () {
    test('base endpoints are correct', () {
      expect(InvenTreeEndpoints.parts, '/api/part/');
      expect(InvenTreeEndpoints.stock, '/api/stock/');
      expect(InvenTreeEndpoints.purchaseOrders, '/api/order/po/');
      expect(InvenTreeEndpoints.salesOrders, '/api/order/so/');
    });

    test('plugin endpoints are correct', () {
      expect(InvenTreeEndpoints.waybillGenerate,
          '/plugin/invoice_print/generate');
    });
  });
}
