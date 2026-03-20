class PurchaseOrder {
  const PurchaseOrder({
    required this.pk,
    required this.reference,
    this.description = '',
    this.supplierId,
    this.supplierDetail,
    this.supplierReference,
    required this.status,
    this.statusText,
    this.lineItemCount = 0,
    this.creationDate,
    this.targetDate,
    this.issueDate,
    this.completeDate,
    this.totalPrice,
    this.totalPriceCurrency,
    this.overdue = false,
  });

  final int pk;
  final String reference;
  final String description;
  final int? supplierId;
  final SupplierRef? supplierDetail;
  final String? supplierReference;
  final int status;
  final String? statusText;
  final int lineItemCount;
  final String? creationDate;
  final String? targetDate;
  final String? issueDate;
  final String? completeDate;
  final double? totalPrice;
  final String? totalPriceCurrency;
  final bool overdue;

  factory PurchaseOrder.fromJson(Map<String, dynamic> json) => PurchaseOrder(
        pk: json['pk'] as int,
        reference: json['reference'] as String,
        description: json['description'] as String? ?? '',
        supplierId: json['supplier'] as int?,
        supplierDetail: json['supplier_detail'] != null
            ? SupplierRef.fromJson(
                json['supplier_detail'] as Map<String, dynamic>)
            : null,
        supplierReference: json['supplier_reference'] as String?,
        status: json['status'] as int,
        statusText: json['status_text'] as String?,
        lineItemCount: json['line_items'] as int? ?? 0,
        creationDate: json['creation_date'] as String?,
        targetDate: json['target_date'] as String?,
        issueDate: json['issue_date'] as String?,
        completeDate: json['complete_date'] as String?,
        totalPrice: (json['total_price'] as num?)?.toDouble(),
        totalPriceCurrency: json['total_price_currency'] as String?,
        overdue: json['overdue'] as bool? ?? false,
      );
}

class SupplierRef {
  const SupplierRef({
    required this.pk,
    required this.name,
    this.image,
    this.thumbnail,
  });

  final int pk;
  final String name;
  final String? image;
  final String? thumbnail;

  factory SupplierRef.fromJson(Map<String, dynamic> json) => SupplierRef(
        pk: json['pk'] as int,
        name: json['name'] as String,
        image: json['image'] as String?,
        thumbnail: json['thumbnail'] as String?,
      );
}
