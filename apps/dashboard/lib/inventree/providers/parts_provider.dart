import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/inventree_client.dart';
import '../models/part.dart';
import '../models/part_category.dart';

export '../models/part_category.dart';

/// Fetch paginated parts list.
/// Family key: search query (null for no filter).
final partsListProvider =
    FutureProvider.autoDispose.family<List<Part>, String?>((ref, search) async {
  final client = ref.watch(inventreeClientProvider);
  final data = await client.getParts(
    limit: 25,
    offset: 0,
    search: search,
  );
  final results = data['results'] as List;
  return results
      .map((e) => Part.fromJson(e as Map<String, dynamic>))
      .toList();
});

/// Fetch a single part by ID.
final partDetailProvider =
    FutureProvider.autoDispose.family<Part, int>((ref, id) async {
  final client = ref.watch(inventreeClientProvider);
  final data = await client.getPart(id);
  return Part.fromJson(data);
});

/// Fetch part categories.
/// Family key: parent category ID (null for top-level).
final partCategoriesProvider =
    FutureProvider.autoDispose.family<List<PartCategory>, int?>(
        (ref, parentId) async {
  final client = ref.watch(inventreeClientProvider);
  final data = await client.getPartCategories(
    limit: 100,
    parentId: parentId,
  );
  final results = data['results'] as List;
  return results
      .map((e) => PartCategory.fromJson(e as Map<String, dynamic>))
      .toList();
});
