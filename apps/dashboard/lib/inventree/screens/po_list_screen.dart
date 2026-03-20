import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shinbee_dashboard/shared/l10n/generated/app_localizations.dart';

import '../providers/orders_provider.dart';
import '../widgets/order_tile.dart';

class POListScreen extends ConsumerWidget {
  const POListScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = S.of(context);
    final ordersAsync = ref.watch(purchaseOrdersProvider(null));

    return Scaffold(
      appBar: AppBar(title: Text(l10n.purchaseOrders)),
      body: ordersAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('${l10n.error}: $e')),
        data: (orders) {
          if (orders.isEmpty) {
            return Center(child: Text(l10n.noResults));
          }
          return ListView.builder(
            itemCount: orders.length,
            itemBuilder: (context, index) =>
                PurchaseOrderTile(order: orders[index]),
          );
        },
      ),
    );
  }
}
