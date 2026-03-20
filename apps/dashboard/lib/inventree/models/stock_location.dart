class StockLocation {
  const StockLocation({
    required this.pk,
    required this.name,
    this.description = '',
    this.parent,
    this.pathstring,
    this.itemCount = 0,
    this.sublocationCount = 0,
    this.icon,
  });

  final int pk;
  final String name;
  final String description;
  final int? parent;
  final String? pathstring;
  final int itemCount;
  final int sublocationCount;
  final String? icon;

  factory StockLocation.fromJson(Map<String, dynamic> json) => StockLocation(
        pk: json['pk'] as int,
        name: json['name'] as String,
        description: json['description'] as String? ?? '',
        parent: json['parent'] as int?,
        pathstring: json['pathstring'] as String?,
        itemCount: json['items'] as int? ?? 0,
        sublocationCount: json['sublocations'] as int? ?? 0,
        icon: json['icon'] as String?,
      );
}
