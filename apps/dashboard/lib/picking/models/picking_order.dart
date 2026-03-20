import 'picking_list_item.dart';

/// A sales order wrapper with company ID and picking progress.
class PickingOrder {
  final int orderId;
  final String reference;
  final String? companyId; // SB-YYMMDD-NNNN format
  final String customerName;
  final String? trackingNumber;
  final DateTime createdDate;
  final int status; // InvenTree SO status
  final List<PickingListItem> items;
  final bool selected; // For multi-select in batch mode

  const PickingOrder({
    required this.orderId,
    required this.reference,
    this.companyId,
    required this.customerName,
    this.trackingNumber,
    required this.createdDate,
    required this.status,
    this.items = const [],
    this.selected = false,
  });

  PickingOrder copyWith({
    String? companyId,
    List<PickingListItem>? items,
    bool? selected,
  }) {
    return PickingOrder(
      orderId: orderId,
      reference: reference,
      companyId: companyId ?? this.companyId,
      customerName: customerName,
      trackingNumber: trackingNumber,
      createdDate: createdDate,
      status: status,
      items: items ?? this.items,
      selected: selected ?? this.selected,
    );
  }

  factory PickingOrder.fromSalesOrder(Map<String, dynamic> so) {
    final customerDetail = so['customer_detail'] as Map<String, dynamic>? ?? {};
    final metadata = so['metadata'] as Map<String, dynamic>? ?? {};
    final picking = metadata['picking'] as Map<String, dynamic>? ?? {};

    return PickingOrder(
      orderId: so['pk'] as int,
      reference: so['reference'] as String? ?? '',
      companyId: picking['company_id'] as String?,
      customerName: customerDetail['name'] as String? ?? 'Unknown',
      trackingNumber: so['link'] as String?,
      createdDate: DateTime.tryParse(so['creation_date'] as String? ?? '') ?? DateTime.now(),
      status: so['status'] as int? ?? 0,
    );
  }

  /// How many items are checked off.
  int get pickedCount => items.where((i) => i.checked).length;

  /// Total items to pick.
  int get totalCount => items.length;

  /// Progress fraction 0.0 - 1.0.
  double get progress => totalCount == 0 ? 0.0 : pickedCount / totalCount;

  /// InvenTree outstanding status codes (10 = Pending, 20 = In Progress).
  bool get isOutstanding => status == 10 || status == 20;
}
