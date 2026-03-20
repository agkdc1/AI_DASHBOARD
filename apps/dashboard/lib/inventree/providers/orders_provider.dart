import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/inventree_client.dart';
import '../models/purchase_order.dart';
import '../models/sales_order.dart';

/// Fetch purchase orders.
/// Family key: outstanding filter (null for all orders).
final purchaseOrdersProvider = FutureProvider.autoDispose
    .family<List<PurchaseOrder>, bool?>((ref, outstanding) async {
  final client = ref.watch(inventreeClientProvider);
  final data = await client.getPurchaseOrders(
    limit: 25,
    offset: 0,
    outstanding: outstanding,
  );
  final results = data['results'] as List;
  return results
      .map((e) => PurchaseOrder.fromJson(e as Map<String, dynamic>))
      .toList();
});

/// Fetch sales orders.
/// Family key: outstanding filter (null for all orders).
final salesOrdersProvider = FutureProvider.autoDispose
    .family<List<SalesOrder>, bool?>((ref, outstanding) async {
  final client = ref.watch(inventreeClientProvider);
  final data = await client.getSalesOrders(
    limit: 25,
    offset: 0,
    outstanding: outstanding,
  );
  final results = data['results'] as List;
  return results
      .map((e) => SalesOrder.fromJson(e as Map<String, dynamic>))
      .toList();
});
