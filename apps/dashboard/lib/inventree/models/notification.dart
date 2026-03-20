class InvenTreeNotification {
  const InvenTreeNotification({
    required this.pk,
    this.message,
    this.creationDate,
    this.read = false,
  });

  final int pk;
  final String? message;
  final String? creationDate;
  final bool read;

  factory InvenTreeNotification.fromJson(Map<String, dynamic> json) =>
      InvenTreeNotification(
        pk: json['pk'] as int,
        message: json['message'] as String?,
        creationDate: json['creation'] as String?,
        read: json['read'] as bool? ?? false,
      );
}
