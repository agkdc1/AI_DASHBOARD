import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/inventree_client.dart';

/// Search InvenTree.
/// Family key: search query string.
final inventreeSearchProvider = FutureProvider.autoDispose
    .family<Map<String, dynamic>, String>((ref, query) async {
  if (query.trim().isEmpty) return {};
  final client = ref.watch(inventreeClientProvider);
  return client.search(query);
});
