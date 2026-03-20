import 'task.dart';

class Bucket {
  const Bucket({
    required this.id,
    required this.title,
    this.position = 0,
    this.projectId = 0,
    this.tasks = const <VikunjaTask>[],
    this.created,
    this.updated,
  });

  final int id;
  final String title;
  final int position;
  final int projectId;
  final List<VikunjaTask> tasks;
  final String? created;
  final String? updated;

  factory Bucket.fromJson(Map<String, dynamic> json) => Bucket(
        id: json['id'] as int,
        title: json['title'] as String,
        position: json['position'] as int? ?? 0,
        projectId: json['project_id'] as int? ?? 0,
        tasks: json['tasks'] != null
            ? (json['tasks'] as List)
                .map((e) => VikunjaTask.fromJson(e as Map<String, dynamic>))
                .toList()
            : const <VikunjaTask>[],
        created: json['created'] as String?,
        updated: json['updated'] as String?,
      );
}
