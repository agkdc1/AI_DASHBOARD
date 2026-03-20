import 'package:flutter_test/flutter_test.dart';
import 'package:shinbee_dashboard/inventree/models/part.dart';
import 'package:shinbee_dashboard/inventree/models/stock.dart';
import 'package:shinbee_dashboard/inventree/models/purchase_order.dart';

void main() {
  group('Part model', () {
    test('fromJson parses correctly', () {
      final json = {
        'pk': 1,
        'name': 'Resistor 10k',
        'description': 'Standard 10k ohm resistor',
        'IPN': 'R-10K',
        'active': true,
        'in_stock': 150.0,
        'on_order': 0.0,
        'assembly': false,
        'component': true,
        'purchaseable': true,
        'salable': false,
        'trackable': false,
        'virtual': false,
      };
      final part = Part.fromJson(json);
      expect(part.pk, 1);
      expect(part.name, 'Resistor 10k');
      expect(part.ipn, 'R-10K');
      expect(part.inStock, 150.0);
      expect(part.component, true);
      expect(part.salable, false);
    });

    test('defaults are applied', () {
      final json = {'pk': 2, 'name': 'Test'};
      final part = Part.fromJson(json);
      expect(part.active, true);
      expect(part.inStock, 0);
      expect(part.assembly, false);
    });
  });

  group('StockItem model', () {
    test('fromJson parses correctly', () {
      final json = {
        'pk': 10,
        'part': 1,
        'quantity': 25.0,
        'serial': null,
        'batch': 'BATCH-001',
        'status': 10,
        'status_text': 'OK',
      };
      final item = StockItem.fromJson(json);
      expect(item.pk, 10);
      expect(item.partId, 1);
      expect(item.quantity, 25.0);
      expect(item.batch, 'BATCH-001');
    });
  });

  group('PurchaseOrder model', () {
    test('fromJson parses correctly', () {
      final json = {
        'pk': 5,
        'reference': 'PO-0005',
        'status': 10,
        'overdue': false,
        'line_items': 3,
        'supplier_detail': {
          'pk': 2,
          'name': 'Digikey',
        },
      };
      final order = PurchaseOrder.fromJson(json);
      expect(order.pk, 5);
      expect(order.reference, 'PO-0005');
      expect(order.lineItemCount, 3);
      expect(order.supplierDetail?.name, 'Digikey');
    });
  });
}
