import 'package:flutter/material.dart';

import '../models/task.dart';

class TaskTile extends StatelessWidget {
  const TaskTile({
    required this.task,
    this.onTap,
    this.onToggleDone,
    super.key,
  });

  final VikunjaTask task;
  final VoidCallback? onTap;
  final ValueChanged<bool>? onToggleDone;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: Checkbox(
        value: task.done,
        onChanged: onToggleDone != null
            ? (v) => onToggleDone!(v ?? false)
            : null,
      ),
      title: Text(
        task.title,
        style: task.done
            ? const TextStyle(decoration: TextDecoration.lineThrough)
            : null,
      ),
      subtitle: _buildSubtitle(context),
      trailing: _priorityIcon(),
      onTap: onTap,
    );
  }

  Widget? _buildSubtitle(BuildContext context) {
    final parts = <Widget>[];
    if (task.dueDate != null && task.dueDate!.isNotEmpty) {
      parts.add(Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.calendar_today, size: 12),
          const SizedBox(width: 4),
          Text(task.dueDate!.substring(0, 10)),
        ],
      ));
    }
    if (task.labels != null && task.labels!.isNotEmpty) {
      parts.add(Wrap(
        spacing: 4,
        children: task.labels!
            .take(3)
            .map((l) => Chip(
                  label: Text(l.title),
                  visualDensity: VisualDensity.compact,
                  padding: EdgeInsets.zero,
                  labelStyle: Theme.of(context).textTheme.bodySmall,
                ))
            .toList(),
      ));
    }
    if (parts.isEmpty) return null;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: parts,
    );
  }

  Widget? _priorityIcon() {
    if (task.priority == 0) return null;
    final color = switch (task.priority) {
      1 => Colors.blue,
      2 => Colors.orange,
      3 => Colors.red,
      _ => Colors.grey,
    };
    return Icon(Icons.flag, color: color, size: 20);
  }
}
