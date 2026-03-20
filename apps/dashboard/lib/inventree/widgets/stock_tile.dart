import 'package:flutter/material.dart';

import '../models/stock.dart';

class StockTile extends StatelessWidget {
  const StockTile({
    required this.item,
    this.onTap,
    super.key,
  });

  final StockItem item;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final partName = item.partDetail?.name ?? 'Part #${item.partId}';
    final location = item.locationDetail?.name ?? 'Unknown';

    return ListTile(
      leading: const Icon(Icons.inventory_2),
      title: Text(partName),
      subtitle: Text(location),
      trailing: Text(
        item.serial != null ? 'S/N: ${item.serial}' : '${item.quantity}',
        style: const TextStyle(fontWeight: FontWeight.bold),
      ),
      onTap: onTap,
    );
  }
}
