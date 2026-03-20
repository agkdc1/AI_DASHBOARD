import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/vikunja_client.dart';
import '../models/project.dart';

/// Fetch all projects.
final projectsListProvider =
    FutureProvider.autoDispose<List<Project>>((ref) async {
  final client = ref.watch(vikunjaClientProvider);
  final data = await client.getProjects();
  return data
      .map((e) => Project.fromJson(e as Map<String, dynamic>))
      .toList();
});

/// Fetch a single project by ID.
final projectDetailProvider =
    FutureProvider.autoDispose.family<Project, int>((ref, id) async {
  final client = ref.watch(vikunjaClientProvider);
  final data = await client.getProject(id);
  return Project.fromJson(data);
});
