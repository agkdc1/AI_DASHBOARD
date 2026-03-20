import 'package:flutter/material.dart';

import '../models/purchase_order.dart';
import '../models/sales_order.dart';

class PurchaseOrderTile extends StatelessWidget {
  const PurchaseOrderTile({
    required this.order,
    this.onTap,
    super.key,
  });

  final PurchaseOrder order;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: Icon(
        Icons.shopping_cart,
        color: order.overdue ? Colors.red : null,
      ),
      title: Text(order.reference),
      subtitle: Text(
        order.supplierDetail?.name ?? order.description,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
      ),
      trailing: _statusChip(context),
      onTap: onTap,
    );
  }

  Widget _statusChip(BuildContext context) {
    return Chip(
      label: Text(
        order.statusText ?? '${order.status}',
        style: Theme.of(context).textTheme.bodySmall,
      ),
      visualDensity: VisualDensity.compact,
    );
  }
}

class SalesOrderTile extends StatelessWidget {
  const SalesOrderTile({
    required this.order,
    this.onTap,
    super.key,
  });

  final SalesOrder order;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: Icon(
        Icons.sell,
        color: order.overdue ? Colors.red : null,
      ),
      title: Text(order.reference),
      subtitle: Text(
        order.customerDetail?.name ?? order.description,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
      ),
      trailing: Chip(
        label: Text(
          order.statusText ?? '${order.status}',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        visualDensity: VisualDensity.compact,
      ),
      onTap: onTap,
    );
  }
}
