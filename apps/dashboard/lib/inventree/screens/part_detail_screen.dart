import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers/parts_provider.dart';

class PartDetailScreen extends ConsumerWidget {
  const PartDetailScreen({required this.partId, super.key});

  final String partId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final id = int.tryParse(partId);
    if (id == null) {
      return Scaffold(
        appBar: AppBar(),
        body: const Center(child: Text('Invalid part ID')),
      );
    }

    final partAsync = ref.watch(partDetailProvider(id));

    return partAsync.when(
      loading: () => Scaffold(
        appBar: AppBar(),
        body: const Center(child: CircularProgressIndicator()),
      ),
      error: (e, _) => Scaffold(
        appBar: AppBar(),
        body: Center(child: Text('Error: $e')),
      ),
      data: (part) => Scaffold(
        appBar: AppBar(title: Text(part.name)),
        body: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            if (part.image != null && part.image!.isNotEmpty)
              Center(
                child: SizedBox(
                  height: 200,
                  child: CachedNetworkImage(
                    imageUrl: part.image!,
                    fit: BoxFit.contain,
                  ),
                ),
              ),
            const SizedBox(height: 16),
            if (part.ipn != null)
              _InfoRow('IPN', part.ipn!),
            if (part.description.isNotEmpty)
              _InfoRow('Description', part.description),
            if (part.categoryDetail != null)
              _InfoRow('Category', part.categoryDetail!.pathstring ?? part.categoryDetail!.name),
            _InfoRow('In Stock', '${part.inStock}${part.units != null ? ' ${part.units}' : ''}'),
            _InfoRow('On Order', '${part.onOrder}'),
            const Divider(height: 32),
            Wrap(
              spacing: 8,
              children: [
                if (part.assembly) const Chip(label: Text('Assembly')),
                if (part.component) const Chip(label: Text('Component')),
                if (part.purchaseable) const Chip(label: Text('Purchaseable')),
                if (part.salable) const Chip(label: Text('Salable')),
                if (part.trackable) const Chip(label: Text('Trackable')),
                if (!part.active)
                  Chip(
                    label: const Text('Inactive'),
                    backgroundColor: Theme.of(context).colorScheme.errorContainer,
                  ),
              ],
            ),
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
