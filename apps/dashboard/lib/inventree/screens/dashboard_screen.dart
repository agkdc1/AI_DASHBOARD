import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shinbee_dashboard/shared/l10n/generated/app_localizations.dart';
import 'package:go_router/go_router.dart';

import '../providers/orders_provider.dart';

class InventoryDashboardScreen extends ConsumerWidget {
  const InventoryDashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = S.of(context);

    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.tabInventory),
        actions: [
          IconButton(
            icon: const Icon(Icons.search),
            onPressed: () {},
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _NavCard(
            title: l10n.parts,
            subtitle: l10n.partCategories,
            icon: Icons.category,
            onTap: () => context.go('/inventory/parts'),
          ),
          _NavCard(
            title: l10n.stock,
            subtitle: l10n.stockLocations,
            icon: Icons.inventory,
            onTap: () => context.go('/inventory/stock'),
          ),
          _NavCard(
            title: l10n.purchaseOrders,
            icon: Icons.shopping_cart,
            onTap: () => context.go('/inventory/orders/purchase'),
          ),
          _NavCard(
            title: l10n.salesOrders,
            icon: Icons.sell,
            onTap: () => context.go('/inventory/orders/sales'),
          ),
          _NavCard(
            title: l10n.waybill,
            icon: Icons.local_shipping,
            onTap: () => context.go('/inventory/waybill'),
          ),
          const SizedBox(height: 16),
          _OutstandingOrdersSummary(),
        ],
      ),
    );
  }
}

class _NavCard extends StatelessWidget {
  const _NavCard({
    required this.title,
    required this.icon,
    required this.onTap,
    this.subtitle,
  });

  final String title;
  final String? subtitle;
  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        leading: Icon(icon, color: Theme.of(context).colorScheme.primary),
        title: Text(title),
        subtitle: subtitle != null ? Text(subtitle!) : null,
        trailing: const Icon(Icons.chevron_right),
        onTap: onTap,
      ),
    );
  }
}

class _OutstandingOrdersSummary extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final poAsync = ref.watch(
      purchaseOrdersProvider(true),
    );
    final soAsync = ref.watch(
      salesOrdersProvider(true),
    );

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Outstanding Orders',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: _OrderCount(
                    label: 'Purchase',
                    count: poAsync.valueOrNull?.length,
                    isLoading: poAsync.isLoading,
                  ),
                ),
                Expanded(
                  child: _OrderCount(
                    label: 'Sales',
                    count: soAsync.valueOrNull?.length,
                    isLoading: soAsync.isLoading,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _OrderCount extends StatelessWidget {
  const _OrderCount({
    required this.label,
    this.count,
    this.isLoading = false,
  });

  final String label;
  final int? count;
  final bool isLoading;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        if (isLoading)
          const SizedBox(
            height: 24,
            width: 24,
            child: CircularProgressIndicator(strokeWidth: 2),
          )
        else
          Text(
            '${count ?? '-'}',
            style: Theme.of(context).textTheme.headlineMedium,
          ),
        Text(label, style: Theme.of(context).textTheme.bodySmall),
      ],
    );
  }
}
