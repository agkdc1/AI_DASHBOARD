class Project {
  const Project({
    required this.id,
    required this.title,
    this.description = '',
    this.isArchived = false,
    this.hexColor = '',
    this.parentProjectId = 0,
    this.created,
    this.updated,
  });

  final int id;
  final String title;
  final String description;
  final bool isArchived;
  final String hexColor;
  final int parentProjectId;
  final String? created;
  final String? updated;

  factory Project.fromJson(Map<String, dynamic> json) => Project(
        id: json['id'] as int,
        title: json['title'] as String,
        description: json['description'] as String? ?? '',
        isArchived: json['is_archived'] as bool? ?? false,
        hexColor: json['hex_color'] as String? ?? '',
        parentProjectId: json['parent_project_id'] as int? ?? 0,
        created: json['created'] as String?,
        updated: json['updated'] as String?,
      );
}
