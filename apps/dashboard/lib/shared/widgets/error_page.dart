import 'package:flutter/material.dart';
import 'package:shinbee_dashboard/shared/l10n/generated/app_localizations.dart';

class ErrorPage extends StatelessWidget {
  const ErrorPage({this.error, super.key});

  final Exception? error;

  @override
  Widget build(BuildContext context) {
    final l10n = S.of(context);

    return Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.error_outline,
              size: 64,
              color: Theme.of(context).colorScheme.error,
            ),
            const SizedBox(height: 16),
            Text(l10n.error, style: Theme.of(context).textTheme.headlineSmall),
            if (error != null) ...[
              const SizedBox(height: 8),
              Text(
                error.toString(),
                style: Theme.of(context).textTheme.bodyMedium,
                textAlign: TextAlign.center,
              ),
            ],
          ],
        ),
      ),
    );
  }
}
