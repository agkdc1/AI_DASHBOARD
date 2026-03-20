class VikunjaTask {
  const VikunjaTask({
    required this.id,
    required this.title,
    this.description = '',
    this.done = false,
    this.doneAt,
    this.priority = 0,
    this.labels,
    this.dueDate,
    this.startDate,
    this.endDate,
    this.repeatAfter = 0,
    this.projectId = 0,
    this.bucketId = 0,
    this.percentDone = 0,
    this.created,
    this.updated,
  });

  final int id;
  final String title;
  final String description;
  final bool done;
  final String? doneAt;
  final int priority;
  final List<Label>? labels;
  final String? dueDate;
  final String? startDate;
  final String? endDate;
  final int repeatAfter;
  final int projectId;
  final int bucketId;
  final double percentDone;
  final String? created;
  final String? updated;

  factory VikunjaTask.fromJson(Map<String, dynamic> json) => VikunjaTask(
        id: json['id'] as int,
        title: json['title'] as String,
        description: json['description'] as String? ?? '',
        done: json['done'] as bool? ?? false,
        doneAt: json['done_at'] as String?,
        priority: json['priority'] as int? ?? 0,
        labels: json['labels'] != null
            ? (json['labels'] as List)
                .map((e) => Label.fromJson(e as Map<String, dynamic>))
                .toList()
            : null,
        dueDate: json['due_date'] as String?,
        startDate: json['start_date'] as String?,
        endDate: json['end_date'] as String?,
        repeatAfter: json['repeat_after'] as int? ?? 0,
        projectId: json['project_id'] as int? ?? 0,
        bucketId: json['bucket_id'] as int? ?? 0,
        percentDone: (json['percent_done'] as num?)?.toDouble() ?? 0,
        created: json['created'] as String?,
        updated: json['updated'] as String?,
      );
}

class Label {
  const Label({
    required this.id,
    required this.title,
    this.hexColor = '',
  });

  final int id;
  final String title;
  final String hexColor;

  factory Label.fromJson(Map<String, dynamic> json) => Label(
        id: json['id'] as int,
        title: json['title'] as String,
        hexColor: json['hex_color'] as String? ?? '',
      );
}
