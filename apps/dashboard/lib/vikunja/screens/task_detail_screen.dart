import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shinbee_dashboard/shared/l10n/generated/app_localizations.dart';

import '../api/vikunja_client.dart';
import '../providers/tasks_provider.dart';

class TaskDetailScreen extends ConsumerWidget {
  const TaskDetailScreen({required this.taskId, super.key});

  final String taskId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = S.of(context);
    final id = int.tryParse(taskId);
    if (id == null) {
      return Scaffold(
        appBar: AppBar(),
        body: const Center(child: Text('Invalid task ID')),
      );
    }

    final taskAsync = ref.watch(taskDetailProvider(id));

    return taskAsync.when(
      loading: () => Scaffold(
        appBar: AppBar(),
        body: const Center(child: CircularProgressIndicator()),
      ),
      error: (e, _) => Scaffold(
        appBar: AppBar(),
        body: Center(child: Text('Error: $e')),
      ),
      data: (task) => Scaffold(
        appBar: AppBar(
          title: Text(task.title),
          actions: [
            IconButton(
              icon: Icon(task.done ? Icons.check_circle : Icons.circle_outlined),
              onPressed: () async {
                final client = ref.read(vikunjaClientProvider);
                await client.updateTask(task.id, {'done': !task.done});
                ref.invalidate(taskDetailProvider(id));
              },
            ),
          ],
        ),
        body: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            if (task.description.isNotEmpty) ...[
              Text(
                task.description,
                style: Theme.of(context).textTheme.bodyLarge,
              ),
              const Divider(height: 32),
            ],
            _InfoRow('Status', task.done ? 'Done' : 'Open'),
            _InfoRow('Priority', _priorityLabel(task.priority)),
            if (task.dueDate != null && task.dueDate!.isNotEmpty)
              _InfoRow('Due Date', task.dueDate!.substring(0, 10)),
            if (task.percentDone > 0)
              _InfoRow('Progress', '${(task.percentDone * 100).toInt()}%'),
            if (task.labels != null && task.labels!.isNotEmpty) ...[
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                children: task.labels!
                    .map((l) => Chip(label: Text(l.title)))
                    .toList(),
              ),
            ],
          ],
        ),
        floatingActionButton: FloatingActionButton(
          onPressed: () async {
            final client = ref.read(vikunjaClientProvider);
            await client.updateTask(task.id, {'done': !task.done});
            ref.invalidate(taskDetailProvider(id));
          },
          child: Icon(task.done ? Icons.undo : Icons.check),
        ),
      ),
    );
  }

  String _priorityLabel(int priority) => switch (priority) {
        0 => 'None',
        1 => 'Low',
        2 => 'Medium',
        3 => 'High',
        _ => 'Unknown',
      };
}

class _InfoRow extends StatelessWidget {
  const _InfoRow(this.label, this.value);

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        children: [
          SizedBox(
            width: 100,
            child: Text(
              label,
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
            ),
          ),
          Expanded(child: Text(value)),
        ],
      ),
    );
  }
}
