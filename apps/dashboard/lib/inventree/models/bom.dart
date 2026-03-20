class BomItem {
  const BomItem({
    required this.pk,
    required this.partId,
    required this.subPartId,
    this.subPartDetail,
    required this.quantity,
    this.reference,
    this.note = '',
  });

  final int pk;
  final int partId;
  final int subPartId;
  final SubPartRef? subPartDetail;
  final double quantity;
  final String? reference;
  final String note;

  factory BomItem.fromJson(Map<String, dynamic> json) => BomItem(
        pk: json['pk'] as int,
        partId: json['part'] as int,
        subPartId: json['sub_part'] as int,
        subPartDetail: json['sub_part_detail'] != null
            ? SubPartRef.fromJson(
                json['sub_part_detail'] as Map<String, dynamic>)
            : null,
        quantity: (json['quantity'] as num).toDouble(),
        reference: json['reference'] as String?,
        note: json['note'] as String? ?? '',
      );
}

class SubPartRef {
  const SubPartRef({
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

  factory SubPartRef.fromJson(Map<String, dynamic> json) => SubPartRef(
        pk: json['pk'] as int,
        name: json['name'] as String,
        description: json['description'] as String?,
        thumbnail: json['thumbnail'] as String?,
        ipn: json['IPN'] as String?,
      );
}
