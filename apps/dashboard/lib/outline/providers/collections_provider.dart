import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/outline_client.dart';
import '../models/collection.dart';

/// Fetch all collections.
final collectionsListProvider =
    FutureProvider.autoDispose<List<OutlineCollection>>((ref) async {
  final client = ref.watch(outlineClientProvider);
  final data = await client.listCollections();
  final results = data['data'] as List? ?? [];
  return results
      .map((e) => OutlineCollection.fromJson(e as Map<String, dynamic>))
      .toList();
});

/// Fetch a single collection by ID.
final collectionDetailProvider = FutureProvider.autoDispose
    .family<OutlineCollection, String>((ref, id) async {
  final client = ref.watch(outlineClientProvider);
  final data = await client.getCollection(id);
  return OutlineCollection.fromJson(data['data'] as Map<String, dynamic>);
});
