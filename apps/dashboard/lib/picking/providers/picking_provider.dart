import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../inventree/api/inventree_client.dart';
import '../models/picking_list_item.dart';
import '../models/picking_order.dart';
import '../models/merged_picking_list.dart';

/// Fetch outstanding sales orders for picking.
final pickingOrdersProvider = FutureProvider.autoDispose<List<PickingOrder>>((ref) async {
  final client = ref.watch(inventreeClientProvider);
  final resp = await client.getSalesOrders(outstanding: true, limit: 100);
  final results = resp['results'] as List? ?? [];
  return results.map((so) => PickingOrder.fromSalesOrder(so as Map<String, dynamic>)).toList();
});

/// State for the picking workflow (selection, check-off, etc).
class PickingState {
  final Map<int, PickingOrder> orders;
  final Set<int> selectedIds;
  final String? scannedBarcode;
  final bool isLoading;

  const PickingState({
    this.orders = const {},
    this.selectedIds = const {},
    this.scannedBarcode,
    this.isLoading = false,
  });

  PickingState copyWith({
    Map<int, PickingOrder>? orders,
    Set<int>? selectedIds,
    String? scannedBarcode,
    bool? isLoading,
  }) {
    return PickingState(
      orders: orders ?? this.orders,
      selectedIds: selectedIds ?? this.selectedIds,
      scannedBarcode: scannedBarcode,
      isLoading: isLoading ?? this.isLoading,
    );
  }
}

class PickingNotifier extends StateNotifier<PickingState> {
  PickingNotifier(this._client) : super(const PickingState());

  final InvenTreeClient _client;

  /// Load line items for a specific sales order.
  Future<void> loadOrderItems(int orderId) async {
    state = state.copyWith(isLoading: true);
    try {
      final resp = await _client.getSalesOrderLines(orderId: orderId);
      final results = resp['results'] as List? ?? [];
      final items = results.map((line) =>
          PickingListItem.fromSalesOrderLine(line as Map<String, dynamic>)).toList()
        ..sort((a, b) => a.sortKey.compareTo(b.sortKey));

      final order = state.orders[orderId];
      if (order != null) {
        final updated = Map<int, PickingOrder>.from(state.orders);
        updated[orderId] = order.copyWith(items: items);
        state = state.copyWith(orders: updated, isLoading: false);
      } else {
        state = state.copyWith(isLoading: false);
      }
    } catch (e) {
      state = state.copyWith(isLoading: false);
    }
  }

  /// Set orders from the list provider.
  void setOrders(List<PickingOrder> orders) {
    final map = {for (final o in orders) o.orderId: o};
    state = state.copyWith(orders: map);
  }

  /// Toggle selection for batch picking.
  void toggleSelection(int orderId) {
    final ids = Set<int>.from(state.selectedIds);
    if (ids.contains(orderId)) {
      ids.remove(orderId);
    } else {
      ids.add(orderId);
    }
    state = state.copyWith(selectedIds: ids);
  }

  /// Select all outstanding orders.
  void selectAll() {
    final ids = state.orders.values
        .where((o) => o.isOutstanding)
        .map((o) => o.orderId)
        .toSet();
    state = state.copyWith(selectedIds: ids);
  }

  /// Clear selection.
  void clearSelection() {
    state = state.copyWith(selectedIds: {});
  }

  /// Check/uncheck a picking item.
  void toggleItemCheck(int orderId, int lineId) {
    final order = state.orders[orderId];
    if (order == null) return;

    final items = order.items.map((item) {
      if (item.lineId == lineId) {
        return item.copyWith(checked: !item.checked);
      }
      return item;
    }).toList();

    final updated = Map<int, PickingOrder>.from(state.orders);
    updated[orderId] = order.copyWith(items: items);
    state = state.copyWith(orders: updated);
  }

  /// Handle barcode scan — find matching order or item.
  void onBarcodeScan(String barcode) {
    state = state.copyWith(scannedBarcode: barcode);
  }

  /// Generate company ID for an order: SB-YYMMDD-NNNN
  Future<String?> generateCompanyId(int orderId) async {
    final now = DateTime.now();
    final datePart = DateFormat('yyMMdd').format(now);

    // Count existing SOs with company IDs for today to get sequence
    int seq = 1;
    for (final o in state.orders.values) {
      if (o.companyId != null && o.companyId!.contains(datePart)) {
        final parts = o.companyId!.split('-');
        if (parts.length == 3) {
          final n = int.tryParse(parts[2]) ?? 0;
          if (n >= seq) seq = n + 1;
        }
      }
    }

    final companyId = 'SB-$datePart-${seq.toString().padLeft(4, '0')}';

    // Save to InvenTree metadata
    try {
      await _client.updateSalesOrderMetadata(orderId, {
        'picking': {'company_id': companyId},
      });

      final updated = Map<int, PickingOrder>.from(state.orders);
      final order = updated[orderId];
      if (order != null) {
        updated[orderId] = order.copyWith(companyId: companyId);
        state = state.copyWith(orders: updated);
      }
      return companyId;
    } catch (e) {
      return null;
    }
  }

  /// Get merged picking list from selected orders.
  List<MergedPickingItem> getMergedList() {
    final orderData = <(int, String, List<PickingListItem>)>[];
    for (final id in state.selectedIds) {
      final order = state.orders[id];
      if (order != null) {
        orderData.add((order.orderId, order.reference, order.items));
      }
    }
    return mergePickingItems(orderData);
  }
}

final pickingNotifierProvider = StateNotifierProvider.autoDispose<PickingNotifier, PickingState>((ref) {
  final client = ref.watch(inventreeClientProvider);
  return PickingNotifier(client);
});
