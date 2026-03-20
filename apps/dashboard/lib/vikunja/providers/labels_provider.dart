import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/vikunja_client.dart';
import '../models/task.dart';

/// Fetch all labels.
final labelsListProvider =
    FutureProvider.autoDispose<List<Label>>((ref) async {
  final client = ref.watch(vikunjaClientProvider);
  final data = await client.getLabels();
  return data.map((e) => Label.fromJson(e as Map<String, dynamic>)).toList();
});
