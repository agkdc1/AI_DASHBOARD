class Part {
  const Part({
    required this.pk,
    required this.name,
    this.description = '',
    this.ipn,
    this.revision,
    this.category,
    this.categoryDetail,
    this.image,
    this.thumbnail,
    this.active = true,
    this.assembly = false,
    this.component = false,
    this.purchaseable = false,
    this.salable = false,
    this.trackable = false,
    this.virtual = false,
    this.inStock = 0,
    this.onOrder = 0,
    this.unallocatedStock = 0,
    this.units,
    this.keywords,
    this.link,
  });

  final int pk;
  final String name;
  final String description;
  final String? ipn;
  final String? revision;
  final int? category;
  final PartCategoryRef? categoryDetail;
  final String? image;
  final String? thumbnail;
  final bool active;
  final bool assembly;
  final bool component;
  final bool purchaseable;
  final bool salable;
  final bool trackable;
  final bool virtual;
  final double inStock;
  final double onOrder;
  final double unallocatedStock;
  final String? units;
  final String? keywords;
  final String? link;

  factory Part.fromJson(Map<String, dynamic> json) => Part(
        pk: json['pk'] as int,
        name: json['name'] as String,
        description: json['description'] as String? ?? '',
        ipn: json['IPN'] as String?,
        revision: json['revision'] as String?,
        category: json['category'] as int?,
        categoryDetail: json['category_detail'] != null
            ? PartCategoryRef.fromJson(
                json['category_detail'] as Map<String, dynamic>)
            : null,
        image: json['image'] as String?,
        thumbnail: json['thumbnail'] as String?,
        active: json['active'] as bool? ?? true,
        assembly: json['assembly'] as bool? ?? false,
        component: json['component'] as bool? ?? false,
        purchaseable: json['purchaseable'] as bool? ?? false,
        salable: json['salable'] as bool? ?? false,
        trackable: json['trackable'] as bool? ?? false,
        virtual: json['virtual'] as bool? ?? false,
        inStock: (json['in_stock'] as num?)?.toDouble() ?? 0,
        onOrder: (json['on_order'] as num?)?.toDouble() ?? 0,
        unallocatedStock:
            (json['unallocated_stock'] as num?)?.toDouble() ?? 0,
        units: json['units'] as String?,
        keywords: json['keywords'] as String?,
        link: json['link'] as String?,
      );
}

class PartCategoryRef {
  const PartCategoryRef({
    required this.pk,
    required this.name,
    this.pathstring,
  });

  final int pk;
  final String name;
  final String? pathstring;

  factory PartCategoryRef.fromJson(Map<String, dynamic> json) =>
      PartCategoryRef(
        pk: json['pk'] as int,
        name: json['name'] as String,
        pathstring: json['pathstring'] as String?,
      );
}
