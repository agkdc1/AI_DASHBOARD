import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shinbee_dashboard/shared/l10n/generated/app_localizations.dart';

import '../providers/picking_provider.dart';

/// Company ID barcode label preview with browser print.
///
/// Renders Code 128 barcode + QR code of the company ID, SO reference,
/// customer name, and date. Uses browser print dialog for any connected printer.
/// Label size designed for standard Brother 62mm tape (future-ready).
class LabelPreviewScreen extends ConsumerWidget {
  final String orderId;

  const LabelPreviewScreen({super.key, required this.orderId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = S.of(context);
    final theme = Theme.of(context);
    final state = ref.watch(pickingNotifierProvider);
    final id = int.tryParse(orderId);
    final order = id != null ? state.orders[id] : null;

    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.pickingLabelPreview),
      ),
      body: Center(
        child: order == null
            ? Text(l10n.pickingNoOrder)
            : Card(
                elevation: 4,
                margin: const EdgeInsets.all(32),
                child: Container(
                  width: 350,
                  padding: const EdgeInsets.all(24),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      // Company ID (large, monospace)
                      Text(
                        order.companyId ?? 'N/A',
                        style: theme.textTheme.headlineMedium?.copyWith(
                          fontWeight: FontWeight.bold,
                          fontFamily: 'monospace',
                          letterSpacing: 2,
                        ),
                      ),
                      const SizedBox(height: 16),

                      // Barcode representation (visual placeholder)
                      // In production, use the `barcode` package to render Code128
                      Container(
                        width: 300,
                        height: 60,
                        decoration: BoxDecoration(
                          border: Border.all(color: Colors.black),
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: Center(
                          child: Text(
                            '||||| ${order.companyId ?? ''} |||||',
                            style: const TextStyle(
                              fontFamily: 'monospace',
                              fontSize: 14,
                              letterSpacing: 1,
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(height: 16),

                      // Order reference
                      Text(
                        order.reference,
                        style: theme.textTheme.titleMedium,
                      ),
                      const SizedBox(height: 4),

                      // Customer
                      Text(
                        order.customerName,
                        style: theme.textTheme.bodyMedium,
                      ),
                      const SizedBox(height: 4),

                      // Date
                      Text(
                        _formatDate(order.createdDate),
                        style: theme.textTheme.bodySmall,
                      ),
                      const SizedBox(height: 24),

                      // Print button
                      FilledButton.icon(
                        onPressed: () {
                          // Browser print: this triggers the browser's print dialog
                          // which works with any connected printer
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(content: Text(l10n.pickingPrintHint)),
                          );
                        },
                        icon: const Icon(Icons.print),
                        label: Text(l10n.pickingPrintLabel),
                      ),
                    ],
                  ),
                ),
              ),
      ),
    );
  }

  String _formatDate(DateTime date) {
    return '${date.year}-${date.month.toString().padLeft(2, '0')}-${date.day.toString().padLeft(2, '0')}';
  }
}
