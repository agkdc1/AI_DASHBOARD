class OutlineDocument {
  const OutlineDocument({
    required this.id,
    required this.title,
    this.text = '',
    this.emoji,
    this.collectionId,
    this.parentDocumentId,
    this.template = false,
    this.archived = false,
    this.createdAt,
    this.updatedAt,
    this.publishedAt,
    this.createdBy,
    this.updatedBy,
  });

  final String id;
  final String title;
  final String text;
  final String? emoji;
  final String? collectionId;
  final String? parentDocumentId;
  final bool template;
  final bool archived;
  final String? createdAt;
  final String? updatedAt;
  final String? publishedAt;
  final DocumentUser? createdBy;
  final DocumentUser? updatedBy;

  factory OutlineDocument.fromJson(Map<String, dynamic> json) =>
      OutlineDocument(
        id: json['id'] as String,
        title: json['title'] as String,
        text: json['text'] as String? ?? '',
        emoji: json['emoji'] as String?,
        collectionId: json['collectionId'] as String?,
        parentDocumentId: json['parentDocumentId'] as String?,
        template: json['template'] as bool? ?? false,
        archived: json['archived'] as bool? ?? false,
        createdAt: json['createdAt'] as String?,
        updatedAt: json['updatedAt'] as String?,
        publishedAt: json['publishedAt'] as String?,
        createdBy: json['createdBy'] != null
            ? DocumentUser.fromJson(json['createdBy'] as Map<String, dynamic>)
            : null,
        updatedBy: json['updatedBy'] != null
            ? DocumentUser.fromJson(json['updatedBy'] as Map<String, dynamic>)
            : null,
      );
}

class DocumentUser {
  const DocumentUser({
    required this.id,
    required this.name,
  });

  final String id;
  final String name;

  factory DocumentUser.fromJson(Map<String, dynamic> json) => DocumentUser(
        id: json['id'] as String,
        name: json['name'] as String,
      );
}
