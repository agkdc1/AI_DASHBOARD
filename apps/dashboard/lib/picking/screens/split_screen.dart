import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:shinbee_dashboard/shared/l10n/generated/app_localizations.dart';

import '../providers/picking_provider.dart';
import '../widgets/barcode_scanner_field.dart';

/// Post-batch split screen: scan order barcodes + product barcodes to assign
/// picked items back to individual orders.
class SplitScreen extends ConsumerStatefulWidget {
  const SplitScreen({super.key});

  @override
  ConsumerState<SplitScreen> createState() => _SplitScreenState();
}

class _SplitScreenState extends ConsumerState<SplitScreen> {
  int? _activeOrderId;
  final Map<int, List<String>> _assignedItems = {}; // orderId → list of IPNs

  @override
  Widget build(BuildContext context) {
    final l10n = S.of(context);
    final theme = Theme.of(context);
    final state = ref.watch(pickingNotifierProvider);

    final selectedOrders = state.selectedIds
        .map((id) => state.orders[id])
        .whereType<dynamic>()
        .toList();

    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.pickingSplitToOrders),
      ),
      body: Column(
        children: [
          // Step 1: Scan order barcode
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  _activeOrderId == null
                      ? l10n.pickingSplitScanOrder
                      : l10n.pickingSplitScanProduct,
                  style: theme.textTheme.titleSmall,
                ),
                const SizedBox(height: 8),
                BarcodeScannerField(
                  hintText: _activeOrderId == null
                      ? l10n.pickingScanHint
                      : l10n.pickingScanProduct,
                  onScanned: _onScan,
                ),
              ],
            ),
          ),

          // Active order indicator
          if (_activeOrderId != null)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              color: theme.colorScheme.primaryContainer,
              child: Row(
                children: [
                  const Icon(Icons.arrow_forward, size: 16),
                  const SizedBox(width: 8),
                  Text(
                    '${l10n.pickingSplitActive}: ${state.orders[_activeOrderId]?.reference ?? ''}',
                    style: theme.textTheme.bodyMedium?.copyWith(
                        fontWeight: FontWeight.bold),
                  ),
                  const Spacer(),
                  TextButton(
                    onPressed: () => setState(() => _activeOrderId = null),
                    child: Text(l10n.pickingSplitSwitch),
                  ),
                ],
              ),
            ),

          // Order cards
          Expanded(
            child: ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: selectedOrders.length,
              itemBuilder: (context, index) {
                final order = selectedOrders[index];
                final assigned = _assignedItems[order.orderId] ?? [];
                final isActive = order.orderId == _activeOrderId;

                return Card(
                  margin: const EdgeInsets.only(bottom: 8),
                  color: isActive
                      ? theme.colorScheme.primaryContainer
                      : null,
                  child: Padding(
                    padding: const EdgeInsets.all(12),
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
                            if (order.companyId != null) ...[
                              const SizedBox(width: 8),
                              Text(order.companyId!,
                                  style: theme.textTheme.bodySmall?.copyWith(
                                      fontFamily: 'monospace')),
                            ],
                          ],
                        ),
                        Text(order.customerName,
                            style: theme.textTheme.bodySmall),
                        const SizedBox(height: 8),
                        Text(
                          '${l10n.pickingSplitAssigned}: ${assigned.length} ${l10n.pickingItems}',
                          style: theme.textTheme.bodyMedium,
                        ),
                        if (assigned.isNotEmpty)
                          Wrap(
                            spacing: 4,
                            children: assigned.map((ipn) => Chip(
                              label: Text(ipn, style: const TextStyle(fontSize: 10)),
                              visualDensity: VisualDensity.compact,
                              materialTapTargetSize:
                                  MaterialTapTargetSize.shrinkWrap,
                            )).toList(),
                          ),
                      ],
                    ),
                  ),
                );
              },
            ),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text(l10n.pickingSplitConfirmed)),
          );
          context.go('/home/picking');
        },
        icon: const Icon(Icons.check),
        label: Text(l10n.pickingSplitConfirm),
      ),
    );
  }

  void _onScan(String barcode) {
    final state = ref.read(pickingNotifierProvider);

    if (_activeOrderId == null) {
      // Looking for an order barcode
      for (final order in state.orders.values) {
        if (order.companyId == barcode ||
            order.reference == barcode ||
            order.trackingNumber == barcode) {
          if (state.selectedIds.contains(order.orderId)) {
            setState(() => _activeOrderId = order.orderId);
            return;
          }
        }
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Order not found: $barcode')),
      );
    } else {
      // Assign product to active order
      setState(() {
        _assignedItems.putIfAbsent(_activeOrderId!, () => []);
        _assignedItems[_activeOrderId!]!.add(barcode);
      });
    }
  }
}
