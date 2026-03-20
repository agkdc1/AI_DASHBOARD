import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shinbee_dashboard/shared/l10n/generated/app_localizations.dart';
import 'package:go_router/go_router.dart';

import '../providers/stock_provider.dart';
import '../widgets/stock_tile.dart';
import '../widgets/search_bar.dart';

class StockListScreen extends ConsumerStatefulWidget {
  const StockListScreen({super.key});

  @override
  ConsumerState<StockListScreen> createState() => _StockListScreenState();
}

class _StockListScreenState extends ConsumerState<StockListScreen> {
  String _search = '';

  @override
  Widget build(BuildContext context) {
    final l10n = S.of(context);
    final stockAsync = ref.watch(
      stockItemsProvider(_search.isEmpty ? null : _search),
    );

    return Scaffold(
      appBar: AppBar(title: Text(l10n.stock)),
      body: Column(
        children: [
          InvenTreeSearchBar(
            onChanged: (v) => setState(() => _search = v),
          ),
          Expanded(
            child: stockAsync.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => Center(child: Text('${l10n.error}: $e')),
              data: (items) {
                if (items.isEmpty) {
                  return Center(child: Text(l10n.noResults));
                }
                return ListView.builder(
                  itemCount: items.length,
                  itemBuilder: (context, index) {
                    final item = items[index];
                    return StockTile(
                      item: item,
                      onTap: () =>
                          context.go('/inventory/stock/${item.pk}'),
                    );
                  },
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}
