import 'package:flutter/material.dart';
import 'package:shinbee_dashboard/shared/l10n/generated/app_localizations.dart';

class PaginatedListView<T> extends StatelessWidget {
  const PaginatedListView({
    required this.items,
    required this.itemBuilder,
    this.isLoading = false,
    this.hasError = false,
    this.onRetry,
    this.onLoadMore,
    this.hasMore = false,
    super.key,
  });

  final List<T> items;
  final Widget Function(BuildContext, T) itemBuilder;
  final bool isLoading;
  final bool hasError;
  final VoidCallback? onRetry;
  final VoidCallback? onLoadMore;
  final bool hasMore;

  @override
  Widget build(BuildContext context) {
    final l10n = S.of(context);

    if (isLoading && items.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }

    if (hasError && items.isEmpty) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(l10n.error),
            if (onRetry != null) ...[
              const SizedBox(height: 8),
              FilledButton(
                onPressed: onRetry,
                child: Text(l10n.retry),
              ),
            ],
          ],
        ),
      );
    }

    if (items.isEmpty) {
      return Center(child: Text(l10n.noResults));
    }

    return ListView.builder(
      itemCount: items.length + (hasMore ? 1 : 0),
      itemBuilder: (context, index) {
        if (index == items.length) {
          if (onLoadMore != null) onLoadMore!();
          return const Center(
            child: Padding(
              padding: EdgeInsets.all(16),
              child: CircularProgressIndicator(),
            ),
          );
        }
        return itemBuilder(context, items[index]);
      },
    );
  }
}
