import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers/stock_provider.dart';

class StockDetailScreen extends ConsumerWidget {
  const StockDetailScreen({required this.stockId, super.key});

  final String stockId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final id = int.tryParse(stockId);
    if (id == null) {
      return Scaffold(
        appBar: AppBar(),
        body: const Center(child: Text('Invalid stock ID')),
      );
    }

    final itemAsync = ref.watch(stockItemDetailProvider(id));

    return itemAsync.when(
      loading: () => Scaffold(
        appBar: AppBar(),
        body: const Center(child: CircularProgressIndicator()),
      ),
      error: (e, _) => Scaffold(
        appBar: AppBar(),
        body: Center(child: Text('Error: $e')),
      ),
      data: (item) => Scaffold(
        appBar: AppBar(
          title: Text(item.partDetail?.name ?? 'Stock #${item.pk}'),
        ),
        body: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            _InfoRow('Quantity', '${item.quantity}'),
            if (item.serial != null) _InfoRow('Serial', item.serial!),
            if (item.batch != null) _InfoRow('Batch', item.batch!),
            if (item.locationDetail != null)
              _InfoRow(
                'Location',
                item.locationDetail!.pathstring ?? item.locationDetail!.name,
              ),
            if (item.statusText != null)
              _InfoRow('Status', item.statusText!),
            if (item.purchasePrice != null)
              _InfoRow(
                'Purchase Price',
                '${item.purchasePrice} ${item.purchasePriceCurrency ?? ''}',
              ),
            if (item.packaging != null)
              _InfoRow('Packaging', item.packaging!),
            if (item.updatedDate != null)
              _InfoRow('Updated', item.updatedDate!),
          ],
        ),
      ),
    );
  }
}

class _InfoRow extends StatelessWidget {
  const _InfoRow(this.label, this.value);

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 120,
            child: Text(
              label,
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
            ),
          ),
          Expanded(child: Text(value)),
        ],
      ),
    );
  }
}
