class SalesOrder {
  const SalesOrder({
    required this.pk,
    required this.reference,
    this.description = '',
    this.customerId,
    this.customerDetail,
    this.customerReference,
    required this.status,
    this.statusText,
    this.lineItemCount = 0,
    this.creationDate,
    this.targetDate,
    this.shipmentDate,
    this.totalPrice,
    this.totalPriceCurrency,
    this.overdue = false,
  });

  final int pk;
  final String reference;
  final String description;
  final int? customerId;
  final CustomerRef? customerDetail;
  final String? customerReference;
  final int status;
  final String? statusText;
  final int lineItemCount;
  final String? creationDate;
  final String? targetDate;
  final String? shipmentDate;
  final double? totalPrice;
  final String? totalPriceCurrency;
  final bool overdue;

  factory SalesOrder.fromJson(Map<String, dynamic> json) => SalesOrder(
        pk: json['pk'] as int,
        reference: json['reference'] as String,
        description: json['description'] as String? ?? '',
        customerId: json['customer'] as int?,
        customerDetail: json['customer_detail'] != null
            ? CustomerRef.fromJson(
                json['customer_detail'] as Map<String, dynamic>)
            : null,
        customerReference: json['customer_reference'] as String?,
        status: json['status'] as int,
        statusText: json['status_text'] as String?,
        lineItemCount: json['line_items'] as int? ?? 0,
        creationDate: json['creation_date'] as String?,
        targetDate: json['target_date'] as String?,
        shipmentDate: json['shipment_date'] as String?,
        totalPrice: (json['total_price'] as num?)?.toDouble(),
        totalPriceCurrency: json['total_price_currency'] as String?,
        overdue: json['overdue'] as bool? ?? false,
      );
}

class CustomerRef {
  const CustomerRef({
    required this.pk,
    required this.name,
    this.image,
    this.thumbnail,
  });

  final int pk;
  final String name;
  final String? image;
  final String? thumbnail;

  factory CustomerRef.fromJson(Map<String, dynamic> json) => CustomerRef(
        pk: json['pk'] as int,
        name: json['name'] as String,
        image: json['image'] as String?,
        thumbnail: json['thumbnail'] as String?,
      );
}
