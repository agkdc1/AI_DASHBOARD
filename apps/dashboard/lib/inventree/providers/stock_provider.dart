import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/inventree_client.dart';
import '../models/stock.dart';

/// Fetch paginated stock items.
/// Family key: search query (null for no filter).
final stockItemsProvider = FutureProvider.autoDispose
    .family<List<StockItem>, String?>((ref, search) async {
  final client = ref.watch(inventreeClientProvider);
  final data = await client.getStockItems(
    limit: 25,
    offset: 0,
    search: search,
  );
  final results = data['results'] as List;
  return results
      .map((e) => StockItem.fromJson(e as Map<String, dynamic>))
      .toList();
});

/// Fetch a single stock item by ID.
final stockItemDetailProvider =
    FutureProvider.autoDispose.family<StockItem, int>((ref, id) async {
  final client = ref.watch(inventreeClientProvider);
  final data = await client.getStockItem(id);
  return StockItem.fromJson(data);
});
