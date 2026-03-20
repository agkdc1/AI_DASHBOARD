import 'package:flutter/material.dart';

import '../models/picking_list_item.dart';

/// Reorderable checklist of picking items with location-based sorting.
class PickingChecklist extends StatelessWidget {
  final List<PickingListItem> items;
  final ValueChanged<int> onToggle; // lineId
  final int? highlightedLineId;

  const PickingChecklist({
    super.key,
    required this.items,
    required this.onToggle,
    this.highlightedLineId,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return ListView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      itemCount: items.length,
      itemBuilder: (context, index) {
        final item = items[index];
        final isHighlighted = item.lineId == highlightedLineId;

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
            onChanged: (_) => onToggle(item.lineId),
            title: Text(
              item.partName,
              style: TextStyle(
                decoration: item.checked
                    ? TextDecoration.lineThrough
                    : null,
                color: item.checked
                    ? theme.disabledColor
                    : null,
              ),
            ),
            subtitle: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (item.ipn.isNotEmpty)
                  Text('IPN: ${item.ipn}',
                      style: theme.textTheme.bodySmall),
                Row(
                  children: [
                    Icon(Icons.inventory_2, size: 14,
                        color: theme.colorScheme.secondary),
                    const SizedBox(width: 4),
                    Text('x${item.quantity.toStringAsFixed(item.quantity == item.quantity.roundToDouble() ? 0 : 1)}',
                        style: theme.textTheme.bodyMedium?.copyWith(
                            fontWeight: FontWeight.bold)),
                    const SizedBox(width: 16),
                    if (item.locationPathstring.isNotEmpty) ...[
                      Icon(Icons.location_on, size: 14,
                          color: theme.colorScheme.tertiary),
                      const SizedBox(width: 4),
                      Expanded(
                        child: Text(item.locationPathstring,
                            style: theme.textTheme.bodySmall,
                            overflow: TextOverflow.ellipsis),
                      ),
                    ],
                  ],
                ),
              ],
            ),
            isThreeLine: true,
            controlAffinity: ListTileControlAffinity.leading,
          ),
        );
      },
    );
  }
}
