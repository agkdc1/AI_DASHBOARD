import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:shinbee_dashboard/shared/l10n/generated/app_localizations.dart';

import '../models/merged_picking_list.dart';
import '../providers/picking_provider.dart';
import '../widgets/barcode_scanner_field.dart';

/// Batch picking screen: merged items from multiple SOs, sorted by location.
class BatchPickingScreen extends ConsumerStatefulWidget {
  const BatchPickingScreen({super.key});

  @override
  ConsumerState<BatchPickingScreen> createState() => _BatchPickingScreenState();
}

class _BatchPickingScreenState extends ConsumerState<BatchPickingScreen> {
  late List<MergedPickingItem> _mergedItems;
  int? _highlightedIndex;

  @override
  void initState() {
    super.initState();
    _mergedItems = [];
  }

  @override
  Widget build(BuildContext context) {
    final l10n = S.of(context);
    final theme = Theme.of(context);
    final state = ref.watch(pickingNotifierProvider);
    final notifier = ref.read(pickingNotifierProvider.notifier);

    // Rebuild merged list from current state
    _mergedItems = notifier.getMergedList();

    final pickedCount = _mergedItems.where((i) => i.checked).length;
    final totalCount = _mergedItems.length;

    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.pickingBatchMode),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 16),
            child: Center(
              child: Text(
                '$pickedCount / $totalCount',
                style: theme.textTheme.titleSmall?.copyWith(
                    fontWeight: FontWeight.bold),
              ),
            ),
          ),
        ],
      ),
      body: Column(
        children: [
          // Selected orders chip bar
          Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            color: theme.colorScheme.surfaceContainerLow,
            child: Wrap(
              spacing: 8,
              children: state.selectedIds.map((id) {
                final order = state.orders[id];
                return Chip(
                  label: Text(order?.reference ?? '#$id',
                      style: const TextStyle(fontSize: 12)),
                  visualDensity: VisualDensity.compact,
                );
              }).toList(),
            ),
          ),

          // Scanner
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
            child: BarcodeScannerField(
              hintText: l10n.pickingScanProduct,
              onScanned: _onProductScan,
            ),
          ),

          // Progress bar
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: LinearProgressIndicator(
              value: totalCount == 0 ? 0 : pickedCount / totalCount,
              minHeight: 6,
              borderRadius: BorderRadius.circular(3),
            ),
          ),

          // Merged list
          Expanded(
            child: _mergedItems.isEmpty
                ? Center(child: Text(l10n.pickingNoItems))
                : ListView.builder(
                    padding: const EdgeInsets.all(16),
                    itemCount: _mergedItems.length,
                    itemBuilder: (context, index) {
                      final item = _mergedItems[index];
                      final isHighlighted = index == _highlightedIndex;

                      return AnimatedContainer(
                        duration: const Duration(milliseconds: 300),
                        decoration: BoxDecoration(
                          color: isHighlighted
                              ? theme.colorScheme.primaryContainer
                              : null,
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: CheckboxListTile(
                          value: item.checked,
                          onChanged: (_) {
                            setState(() {
                              _mergedItems[index] =
                                  item.copyWith(checked: !item.checked);
                            });
                          },
                          title: Text(
                            item.partName,
                            style: TextStyle(
                              decoration: item.checked
                                  ? TextDecoration.lineThrough
                                  : null,
                            ),
                          ),
                          subtitle: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  Text('IPN: ${item.ipn}',
                                      style: theme.textTheme.bodySmall),
                                  const Spacer(),
                                  Text(
                                    'x${item.totalQuantity.toStringAsFixed(0)}',
                                    style: theme.textTheme.bodyLarge?.copyWith(
                                        fontWeight: FontWeight.bold),
                                  ),
                                ],
                              ),
                              if (item.locationPathstring.isNotEmpty)
                                Row(
                                  children: [
                                    Icon(Icons.location_on, size: 14,
                                        color: theme.colorScheme.tertiary),
                                    const SizedBox(width: 4),
                                    Text(item.locationPathstring,
                                        style: theme.textTheme.bodySmall),
                                  ],
                                ),
                              // Per-order breakdown
                              Wrap(
                                spacing: 4,
                                children: item.orderBreakdowns.map((b) {
                                  return Chip(
                                    label: Text(
                                      '${b.reference}: x${b.quantity.toStringAsFixed(0)}',
                                      style: const TextStyle(fontSize: 10),
                                    ),
                                    visualDensity: VisualDensity.compact,
                                    materialTapTargetSize:
                                        MaterialTapTargetSize.shrinkWrap,
                                  );
                                }).toList(),
                              ),
                            ],
                          ),
                          isThreeLine: true,
                          controlAffinity: ListTileControlAffinity.leading,
                        ),
                      );
                    },
                  ),
          ),
        ],
      ),
      floatingActionButton: pickedCount == totalCount && totalCount > 0
          ? FloatingActionButton.extended(
              onPressed: () => context.go('/home/picking/split'),
              icon: const Icon(Icons.call_split),
              label: Text(l10n.pickingSplitToOrders),
            )
          : null,
    );
  }

  void _onProductScan(String barcode) {
    for (int i = 0; i < _mergedItems.length; i++) {
      if (_mergedItems[i].ipn == barcode) {
        setState(() {
          _highlightedIndex = i;
          _mergedItems[i] = _mergedItems[i].copyWith(checked: true);
        });
        Future.delayed(const Duration(seconds: 2), () {
          if (mounted) setState(() => _highlightedIndex = null);
        });
        return;
      }
    }
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('Product not found: $barcode')),
    );
  }
}
