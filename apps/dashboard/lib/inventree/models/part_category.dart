class PartCategory {
  const PartCategory({
    required this.pk,
    required this.name,
    this.description = '',
    this.parent,
    this.pathstring,
    this.partCount = 0,
    this.subcategoryCount = 0,
    this.icon,
  });

  final int pk;
  final String name;
  final String description;
  final int? parent;
  final String? pathstring;
  final int partCount;
  final int subcategoryCount;
  final String? icon;

  factory PartCategory.fromJson(Map<String, dynamic> json) => PartCategory(
        pk: json['pk'] as int,
        name: json['name'] as String,
        description: json['description'] as String? ?? '',
        parent: json['parent'] as int?,
        pathstring: json['pathstring'] as String?,
        partCount: json['part_count'] as int? ?? 0,
        subcategoryCount: json['subcategories'] as int? ?? 0,
        icon: json['icon'] as String?,
      );
}
