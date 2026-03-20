import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shinbee_dashboard/shared/l10n/generated/app_localizations.dart';
import 'package:go_router/go_router.dart';

import '../providers/projects_provider.dart';

class ProjectsScreen extends ConsumerWidget {
  const ProjectsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = S.of(context);
    final projectsAsync = ref.watch(projectsListProvider);

    return Scaffold(
      appBar: AppBar(title: Text(l10n.projects)),
      body: projectsAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('${l10n.error}: $e')),
        data: (projects) {
          if (projects.isEmpty) {
            return Center(child: Text(l10n.noResults));
          }
          return ListView.builder(
            itemCount: projects.length,
            itemBuilder: (context, index) {
              final project = projects[index];
              return ListTile(
                leading: CircleAvatar(
                  backgroundColor: project.hexColor.isNotEmpty
                      ? Color(int.parse('FF${project.hexColor}', radix: 16))
                      : null,
                  child: Text(
                    project.title.isNotEmpty ? project.title[0].toUpperCase() : '?',
                  ),
                ),
                title: Text(project.title),
                subtitle: project.description.isNotEmpty
                    ? Text(project.description, maxLines: 1, overflow: TextOverflow.ellipsis)
                    : null,
                trailing: project.isArchived
                    ? const Icon(Icons.archive, size: 16)
                    : const Icon(Icons.chevron_right),
                onTap: () => context.go('/tasks/${project.id}'),
              );
            },
          );
        },
      ),
    );
  }
}
