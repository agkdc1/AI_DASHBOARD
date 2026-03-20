import 'package:flutter/material.dart';

import '../models/bucket.dart';
import '../models/task.dart';
import 'task_tile.dart';

class KanbanColumn extends StatelessWidget {
  const KanbanColumn({
    required this.bucket,
    this.onTaskTap,
    super.key,
  });

  final Bucket bucket;
  final void Function(VikunjaTask)? onTaskTap;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 280,
      margin: const EdgeInsets.symmetric(horizontal: 8),
      child: Card(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsets.all(12),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      bucket.title,
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                  ),
                  Text(
                    '${bucket.tasks.length}',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ),
            ),
            const Divider(height: 1),
            Expanded(
              child: ListView.builder(
                itemCount: bucket.tasks.length,
                itemBuilder: (context, index) {
                  final task = bucket.tasks[index];
                  return TaskTile(
                    task: task,
                    onTap: () => onTaskTap?.call(task),
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}
