import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/vikunja_client.dart';
import '../models/bucket.dart';
import '../models/task.dart';

/// Fetch tasks for a project.
/// Family key: project ID.
final projectTasksProvider = FutureProvider.autoDispose
    .family<List<VikunjaTask>, int>((ref, projectId) async {
  final client = ref.watch(vikunjaClientProvider);
  final data = await client.getProjectTasks(projectId);
  return data
      .map((e) => VikunjaTask.fromJson(e as Map<String, dynamic>))
      .toList();
});

/// Fetch a single task by ID.
final taskDetailProvider =
    FutureProvider.autoDispose.family<VikunjaTask, int>((ref, id) async {
  final client = ref.watch(vikunjaClientProvider);
  final data = await client.getTask(id);
  return VikunjaTask.fromJson(data);
});

/// Fetch kanban buckets for a project.
/// Family key: project ID.
final projectBucketsProvider = FutureProvider.autoDispose
    .family<List<Bucket>, int>((ref, projectId) async {
  final client = ref.watch(vikunjaClientProvider);
  final data = await client.getBuckets(projectId);
  return data
      .map((e) => Bucket.fromJson(e as Map<String, dynamic>))
      .toList();
});
