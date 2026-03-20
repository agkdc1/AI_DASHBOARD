import 'picking_list_item.dart';

/// A merged line item from multiple SOs, grouped by part + location.
class MergedPickingItem {
  final int partId;
  final String partName;
  final String ipn;
  final double totalQuantity;
  final String locationPathstring;
  final int? locationId;
  final List<OrderBreakdown> orderBreakdowns;
  final bool checked;

  const MergedPickingItem({
    required this.partId,
    required this.partName,
    required this.ipn,
    required this.totalQuantity,
    required this.locationPathstring,
    this.locationId,
    required this.orderBreakdowns,
    this.checked = false,
  });

  MergedPickingItem copyWith({bool? checked}) {
    return MergedPickingItem(
      partId: partId,
      partName: partName,
      ipn: ipn,
      totalQuantity: totalQuantity,
      locationPathstring: locationPathstring,
      locationId: locationId,
      orderBreakdowns: orderBreakdowns,
      checked: checked ?? this.checked,
    );
  }
}

/// Quantity breakdown per originating SO.
class OrderBreakdown {
  final int orderId;
  final String reference;
  final double quantity;

  const OrderBreakdown({
    required this.orderId,
    required this.reference,
    required this.quantity,
  });
}

/// Merge items from multiple SOs, grouping by part + location.
List<MergedPickingItem> mergePickingItems(
  List<(int orderId, String reference, List<PickingListItem> items)> orders,
) {
  final grouped = <String, MergedPickingItem>{};

  for (final (orderId, reference, items) in orders) {
    for (final item in items) {
      final key = '${item.partId}:${item.locationPathstring}';
      final existing = grouped[key];
      if (existing != null) {
        grouped[key] = MergedPickingItem(
          partId: item.partId,
          partName: item.partName,
          ipn: item.ipn,
          totalQuantity: existing.totalQuantity + item.quantity,
          locationPathstring: item.locationPathstring,
          locationId: item.locationId,
          orderBreakdowns: [
            ...existing.orderBreakdowns,
            OrderBreakdown(orderId: orderId, reference: reference, quantity: item.quantity),
          ],
        );
      } else {
        grouped[key] = MergedPickingItem(
          partId: item.partId,
          partName: item.partName,
          ipn: item.ipn,
          totalQuantity: item.quantity,
          locationPathstring: item.locationPathstring,
          locationId: item.locationId,
          orderBreakdowns: [
            OrderBreakdown(orderId: orderId, reference: reference, quantity: item.quantity),
          ],
        );
      }
    }
  }

  // Sort by location for warehouse-walk efficiency
  final result = grouped.values.toList()
    ..sort((a, b) => a.locationPathstring.compareTo(b.locationPathstring));
  return result;
}
