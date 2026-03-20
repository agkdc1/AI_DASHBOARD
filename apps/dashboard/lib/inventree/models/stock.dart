class StockItem {
  const StockItem({
    required this.pk,
    required this.partId,
    this.partDetail,
    this.location,
    this.locationDetail,
    required this.quantity,
    this.serial,
    this.batch,
    this.status,
    this.statusText,
    this.purchasePrice,
    this.purchasePriceCurrency,
    this.packaging,
    this.link,
    this.updatedDate,
  });

  final int pk;
  final int partId;
  final PartRef? partDetail;
  final int? location;
  final LocationRef? locationDetail;
  final double quantity;
  final String? serial;
  final String? batch;
  final int? status;
  final String? statusText;
  final double? purchasePrice;
  final String? purchasePriceCurrency;
  final String? packaging;
  final String? link;
  final String? updatedDate;

  factory StockItem.fromJson(Map<String, dynamic> json) => StockItem(
        pk: json['pk'] as int,
        partId: json['part'] as int,
        partDetail: json['part_detail'] != null
            ? PartRef.fromJson(json['part_detail'] as Map<String, dynamic>)
            : null,
        location: json['location'] as int?,
        locationDetail: json['location_detail'] != null
            ? LocationRef.fromJson(
                json['location_detail'] as Map<String, dynamic>)
            : null,
        quantity: (json['quantity'] as num).toDouble(),
        serial: json['serial'] as String?,
        batch: json['batch'] as String?,
        status: json['status'] as int?,
        statusText: json['status_text'] as String?,
        purchasePrice: (json['purchase_price'] as num?)?.toDouble(),
        purchasePriceCurrency: json['purchase_price_currency'] as String?,
        packaging: json['packaging'] as String?,
        link: json['link'] as String?,
        updatedDate: json['updated'] as String?,
      );
}

class PartRef {
  const PartRef({
    required this.pk,
    required this.name,
    this.description,
    this.thumbnail,
    this.ipn,
  });

  final int pk;
  final String name;
  final String? description;
  final String? thumbnail;
  final String? ipn;

  factory PartRef.fromJson(Map<String, dynamic> json) => PartRef(
        pk: json['pk'] as int,
        name: json['name'] as String,
        description: json['description'] as String?,
        thumbnail: json['thumbnail'] as String?,
        ipn: json['IPN'] as String?,
      );
}

class LocationRef {
  const LocationRef({
    required this.pk,
    required this.name,
    this.pathstring,
  });

  final int pk;
  final String name;
  final String? pathstring;

  factory LocationRef.fromJson(Map<String, dynamic> json) => LocationRef(
        pk: json['pk'] as int,
        name: json['name'] as String,
        pathstring: json['pathstring'] as String?,
      );
}
