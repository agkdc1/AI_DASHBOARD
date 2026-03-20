class OutlineCollection {
  const OutlineCollection({
    required this.id,
    required this.name,
    this.description = '',
    this.color,
    this.icon,
    this.index,
    this.permission = 'read_write',
    this.createdAt,
    this.updatedAt,
  });

  final String id;
  final String name;
  final String description;
  final String? color;
  final String? icon;
  final int? index;
  final String permission;
  final String? createdAt;
  final String? updatedAt;

  factory OutlineCollection.fromJson(Map<String, dynamic> json) =>
      OutlineCollection(
        id: json['id'] as String,
        name: json['name'] as String,
        description: json['description'] as String? ?? '',
        color: json['color'] as String?,
        icon: json['icon'] as String?,
        index: json['index'] as int?,
        permission: json['permission'] as String? ?? 'read_write',
        createdAt: json['createdAt'] as String?,
        updatedAt: json['updatedAt'] as String?,
      );
}
