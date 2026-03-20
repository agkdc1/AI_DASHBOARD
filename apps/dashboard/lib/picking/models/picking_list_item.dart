/// A single line item in a picking list (sales order line + allocation).
class PickingListItem {
  final int lineId;
  final int partId;
  final String partName;
  final String ipn; // Internal Part Number
  final double quantity;
  final double allocatedQuantity;
  final int? locationId;
  final String locationPathstring;
  final bool checked;

  const PickingListItem({
    required this.lineId,
    required this.partId,
    required this.partName,
    required this.ipn,
    required this.quantity,
    this.allocatedQuantity = 0,
    this.locationId,
    this.locationPathstring = '',
    this.checked = false,
  });

  PickingListItem copyWith({
    bool? checked,
    double? allocatedQuantity,
  }) {
    return PickingListItem(
      lineId: lineId,
      partId: partId,
      partName: partName,
      ipn: ipn,
      quantity: quantity,
      allocatedQuantity: allocatedQuantity ?? this.allocatedQuantity,
      locationId: locationId,
      locationPathstring: locationPathstring,
      checked: checked ?? this.checked,
    );
  }

  factory PickingListItem.fromSalesOrderLine(Map<String, dynamic> line) {
    final partDetail = line['part_detail'] as Map<String, dynamic>? ?? {};
    return PickingListItem(
      lineId: line['pk'] as int,
      partId: line['part'] as int,
      partName: partDetail['full_name'] as String? ?? partDetail['name'] as String? ?? 'Unknown',
      ipn: partDetail['IPN'] as String? ?? '',
      quantity: (line['quantity'] as num).toDouble(),
      allocatedQuantity: (line['allocated'] as num?)?.toDouble() ?? 0,
    );
  }

  /// Sort key for warehouse walk efficiency (by location pathstring).
  String get sortKey => locationPathstring.isEmpty ? 'zzz' : locationPathstring;
}
