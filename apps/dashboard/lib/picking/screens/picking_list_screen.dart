import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:shinbee_dashboard/shared/l10n/generated/app_localizations.dart';

import '../providers/picking_provider.dart';
import '../widgets/barcode_scanner_field.dart';

/// Main picking list screen: outstanding SOs with multi-select for batch picking.
class PickingListScreen extends ConsumerStatefulWidget {
  const PickingListScreen({super.key});

  @override
  ConsumerState<PickingListScreen> createState() => _PickingListScreenState();
}

class _PickingListScreenState extends ConsumerState<PickingListScreen> {
  @override
  Widget build(BuildContext context) {
    final l10n = S.of(context);
    final theme = Theme.of(context);
    final ordersAsync = ref.watch(pickingOrdersProvider);
    final pickingState = ref.watch(pickingNotifierProvider);
    final notifier = ref.read(pickingNotifierProvider.notifier);

    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.pickingList),
        actions: [
          if (pickingState.selectedIds.isNotEmpty)
            TextButton.icon(
              onPressed: () => notifier.clearSelection(),
              icon: const Icon(Icons.clear),
              label: Text('${pickingState.selectedIds.length}'),
            ),
          IconButton(
            icon: const Icon(Icons.select_all),
            tooltip: l10n.pickingSelectAll,
            onPressed: () => notifier.selectAll(),
          ),
        ],
      ),
      body: Column(
        children: [
          // Barcode scanner field
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
            child: BarcodeScannerField(
              hintText: l10n.pickingScanHint,
              onScanned: (barcode) => _onBarcodeScan(barcode, notifier, pickingState),
            ),
          ),

          // Order list
          Expanded(
            child: ordersAsync.when(
              data: (orders) {
                // Set orders in state notifier
                WidgetsBinding.instance.addPostFrameCallback((_) {
                  notifier.setOrders(orders);
                });

                if (orders.isEmpty) {
                  return Center(child: Text(l10n.pickingNoOrders));
                }

                return ListView.builder(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  itemCount: orders.length,
                  itemBuilder: (context, index) {
                    final order = orders[index];
                    final isSelected = pickingState.selectedIds.contains(order.orderId);

                    return Card(
                      margin: const EdgeInsets.only(bottom: 8),
                      color: isSelected
                          ? theme.colorScheme.primaryContainer
                          : null,
                      child: InkWell(
                        onTap: () => context.go('/home/picking/order/${order.orderId}'),
                        onLongPress: () => notifier.toggleSelection(order.orderId),
                        borderRadius: BorderRadius.circular(12),
                        child: Padding(
                          padding: const EdgeInsets.all(12),
                          child: Row(
                            children: [
                              // Selection checkbox
                              Checkbox(
                                value: isSelected,
                                onChanged: (_) => notifier.toggleSelection(order.orderId),
                              ),
                              // Order info
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Row(
                                      children: [
                                        Text(
                                          order.reference,
                                          style: theme.textTheme.titleSmall?.copyWith(
                                              fontWeight: FontWeight.bold),
                                        ),
                                        const SizedBox(width: 8),
                                        if (order.companyId != null)
                                          Chip(
                                            label: Text(order.companyId!,
                                                style: const TextStyle(fontSize: 11)),
                                            materialTapTargetSize:
                                                MaterialTapTargetSize.shrinkWrap,
                                            visualDensity: VisualDensity.compact,
                                          ),
                                      ],
                                    ),
                                    const SizedBox(height: 4),
                                    Text(order.customerName,
                                        style: theme.textTheme.bodySmall),
                                  ],
                                ),
                              ),
                              // Generate ID / label button
                              if (order.companyId == null)
                                TextButton(
                                  onPressed: () async {
                                    await notifier.generateCompanyId(order.orderId);
                                  },
                                  child: Text(l10n.pickingGenerateId),
                                )
                              else
                                IconButton(
                                  icon: const Icon(Icons.print, size: 20),
                                  tooltip: l10n.pickingPrintLabel,
                                  onPressed: () => context.go(
                                      '/home/picking/label/${order.orderId}'),
                                ),
                            ],
                          ),
                        ),
                      ),
                    );
                  },
                );
              },
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => Center(child: Text('${l10n.error}: $e')),
            ),
          ),
        ],
      ),
      // Batch pick FAB
      floatingActionButton: pickingState.selectedIds.length >= 2
          ? FloatingActionButton.extended(
              onPressed: () => context.go('/home/picking/batch'),
              icon: const Icon(Icons.merge),
              label: Text(l10n.pickingStartBatch),
            )
          : null,
    );
  }

  void _onBarcodeScan(String barcode, PickingNotifier notifier, PickingState state) {
    // Check if barcode matches a company ID (SB-YYMMDD-NNNN)
    for (final order in state.orders.values) {
      if (order.companyId == barcode) {
        context.go('/home/picking/order/${order.orderId}');
        return;
      }
    }
    // Check if barcode matches a reference
    for (final order in state.orders.values) {
      if (order.reference == barcode || order.trackingNumber == barcode) {
        context.go('/home/picking/order/${order.orderId}');
        return;
      }
    }
    // Not found — show snackbar
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('Barcode not found: $barcode')),
    );
  }
}
