import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../providers/tasks_provider.dart';
import '../widgets/task_tile.dart';

class ProjectDetailScreen extends ConsumerWidget {
  const ProjectDetailScreen({required this.projectId, super.key});

  final String projectId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final id = int.tryParse(projectId);
    if (id == null) {
      return Scaffold(
        appBar: AppBar(),
        body: const Center(child: Text('Invalid project ID')),
      );
    }

    final tasksAsync = ref.watch(projectTasksProvider(id));

    return Scaffold(
      appBar: AppBar(
        title: Text('Project #$projectId'),
        actions: [
          IconButton(
            icon: const Icon(Icons.view_kanban),
            tooltip: 'Kanban',
            onPressed: () => context.go('/tasks/$projectId/kanban'),
          ),
          IconButton(
            icon: const Icon(Icons.calendar_month),
            tooltip: 'Calendar',
            onPressed: () => context.go('/tasks/$projectId/calendar'),
          ),
        ],
      ),
      body: tasksAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Error: $e')),
        data: (tasks) {
          if (tasks.isEmpty) {
            return const Center(child: Text('No tasks'));
          }
          return ListView.builder(
            itemCount: tasks.length,
            itemBuilder: (context, index) {
              final task = tasks[index];
              return TaskTile(
                task: task,
                onTap: () => context.go('/tasks/task/${task.id}'),
              );
            },
          );
        },
      ),
    );
  }
}
