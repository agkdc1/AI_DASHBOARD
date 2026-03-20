import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/outline_client.dart';
import '../models/document.dart';

/// Fetch documents list.
/// Family key: collection ID filter (null for all documents).
final documentsListProvider = FutureProvider.autoDispose
    .family<List<OutlineDocument>, String?>((ref, collectionId) async {
  final client = ref.watch(outlineClientProvider);
  final data = await client.listDocuments(
    collectionId: collectionId,
    limit: 25,
    offset: 0,
  );
  final results = data['data'] as List? ?? [];
  return results
      .map((e) => OutlineDocument.fromJson(e as Map<String, dynamic>))
      .toList();
});

/// Fetch a single document by ID.
final documentDetailProvider = FutureProvider.autoDispose
    .family<OutlineDocument, String>((ref, id) async {
  final client = ref.watch(outlineClientProvider);
  final data = await client.getDocument(id);
  return OutlineDocument.fromJson(data['data'] as Map<String, dynamic>);
});
