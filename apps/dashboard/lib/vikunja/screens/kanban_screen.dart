import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shinbee_dashboard/shared/l10n/generated/app_localizations.dart';
import 'package:go_router/go_router.dart';

import '../providers/tasks_provider.dart';
import '../widgets/kanban_column.dart';

class KanbanScreen extends ConsumerWidget {
  const KanbanScreen({required this.projectId, super.key});

  final String projectId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = S.of(context);
    final id = int.tryParse(projectId);
    if (id == null) {
      return Scaffold(
        appBar: AppBar(title: Text(l10n.kanban)),
        body: const Center(child: Text('Invalid project ID')),
      );
    }

    final bucketsAsync = ref.watch(projectBucketsProvider(id));

    return Scaffold(
      appBar: AppBar(title: Text(l10n.kanban)),
      body: bucketsAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('${l10n.error}: $e')),
        data: (buckets) {
          if (buckets.isEmpty) {
            return Center(child: Text(l10n.noResults));
          }
          return ListView.builder(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.all(8),
            itemCount: buckets.length,
            itemBuilder: (context, index) => KanbanColumn(
              bucket: buckets[index],
              onTaskTap: (task) => context.go('/tasks/task/${task.id}'),
            ),
          );
        },
      ),
    );
  }
}
