class Attachment {
  const Attachment({
    required this.pk,
    this.modelType,
    this.modelId,
    this.attachment,
    this.filename,
    this.comment,
    this.uploadDate,
  });

  final int pk;
  final String? modelType;
  final int? modelId;
  final String? attachment;
  final String? filename;
  final String? comment;
  final String? uploadDate;

  factory Attachment.fromJson(Map<String, dynamic> json) => Attachment(
        pk: json['pk'] as int,
        modelType: json['model_type'] as String?,
        modelId: json['model_id'] as int?,
        attachment: json['attachment'] as String?,
        filename: json['filename'] as String?,
        comment: json['comment'] as String?,
        uploadDate: json['upload_date'] as String?,
      );
}
