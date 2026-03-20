import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:shinbee_dashboard/shared/l10n/generated/app_localizations.dart';

import '../providers/picking_provider.dart';
import '../widgets/barcode_scanner_field.dart';
import '../widgets/picking_checklist.dart';

/// Single order picking screen with checklist and barcode scan-to-find.
class PickingOrderScreen extends ConsumerStatefulWidget {
  final String orderId;

  const PickingOrderScreen({super.key, required this.orderId});

  @override
  ConsumerState<PickingOrderScreen> createState() => _PickingOrderScreenState();
}

class _PickingOrderScreenState extends ConsumerState<PickingOrderScreen> {
  int? _highlightedLineId;

  @override
  void initState() {
    super.initState();
    final id = int.tryParse(widget.orderId);
    if (id != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        ref.read(pickingNotifierProvider.notifier).loadOrderItems(id);
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = S.of(context);
    final theme = Theme.of(context);
    final state = ref.watch(pickingNotifierProvider);
    final notifier = ref.read(pickingNotifierProvider.notifier);
    final orderId = int.tryParse(widget.orderId);
    final order = orderId != null ? state.orders[orderId] : null;

    return Scaffold(
      appBar: AppBar(
        title: Text(order?.reference ?? l10n.pickingOrder),
        actions: [
          if (order?.companyId != null)
            IconButton(
              icon: const Icon(Icons.print),
              tooltip: l10n.pickingPrintLabel,
              onPressed: () => context.go('/home/picking/label/$orderId'),
            ),
        ],
      ),
      body: order == null
          ? const Center(child: CircularProgressIndicator())
          : Column(
              children: [
                // Header info
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(16),
                  color: theme.colorScheme.surfaceContainerLow,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      if (order.companyId != null)
                        Text(order.companyId!,
                            style: theme.textTheme.titleMedium?.copyWith(
                                fontWeight: FontWeight.bold,
                                fontFamily: 'monospace')),
                      Text('${l10n.pickingCustomer}: ${order.customerName}',
                          style: theme.textTheme.bodyMedium),
                      if (order.trackingNumber != null)
                        Text('Tracking: ${order.trackingNumber}',
                            style: theme.textTheme.bodySmall),
                      const SizedBox(height: 8),
                      // Progress bar
                      Row(
                        children: [
                          Expanded(
                            child: LinearProgressIndicator(
                              value: order.progress,
                              minHeight: 8,
                              borderRadius: BorderRadius.circular(4),
                            ),
                          ),
                          const SizedBox(width: 12),
                          Text(
                            '${order.pickedCount} / ${order.totalCount}',
                            style: theme.textTheme.bodySmall?.copyWith(
                                fontWeight: FontWeight.bold),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),

                // Barcode scanner for product IPN lookup
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
                  child: BarcodeScannerField(
                    hintText: l10n.pickingScanProduct,
                    onScanned: (barcode) => _onProductScan(barcode, order),
                  ),
                ),

                // Checklist
                Expanded(
                  child: state.isLoading
                      ? const Center(child: CircularProgressIndicator())
                      : SingleChildScrollView(
                          padding: const EdgeInsets.all(16),
                          child: PickingChecklist(
                            items: order.items,
                            highlightedLineId: _highlightedLineId,
                            onToggle: (lineId) {
                              if (orderId != null) {
                                notifier.toggleItemCheck(orderId, lineId);
                              }
                            },
                          ),
                        ),
                ),
              ],
            ),
      floatingActionButton: order != null && order.pickedCount == order.totalCount
          ? FloatingActionButton.extended(
              onPressed: () {
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(content: Text(l10n.pickingComplete)),
                );
              },
              icon: const Icon(Icons.check_circle),
              label: Text(l10n.pickingCompletePick),
            )
          : null,
    );
  }

  void _onProductScan(String barcode, dynamic order) {
    // Find item by IPN match
    if (order == null) return;
    for (final item in order.items) {
      if (item.ipn == barcode || item.partName.contains(barcode)) {
        setState(() => _highlightedLineId = item.lineId);
        Future.delayed(const Duration(seconds: 3), () {
          if (mounted) setState(() => _highlightedLineId = null);
        });
        return;
      }
    }
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('Product not found: $barcode')),
    );
  }
}
