import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/outline_client.dart';
import '../models/search_result.dart';

/// Search Outline documents.
/// Family key: search query string.
final outlineSearchProvider = FutureProvider.autoDispose
    .family<List<SearchResult>, String>((ref, query) async {
  if (query.trim().isEmpty) return [];
  final client = ref.watch(outlineClientProvider);
  final data = await client.searchDocuments(query);
  final results = data['data'] as List? ?? [];
  return results
      .map((e) => SearchResult.fromJson(e as Map<String, dynamic>))
      .toList();
});
