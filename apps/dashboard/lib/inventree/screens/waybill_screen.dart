import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shinbee_dashboard/shared/l10n/generated/app_localizations.dart';

import '../api/inventree_client.dart';

class WaybillScreen extends ConsumerStatefulWidget {
  const WaybillScreen({super.key});

  @override
  ConsumerState<WaybillScreen> createState() => _WaybillScreenState();
}

class _WaybillScreenState extends ConsumerState<WaybillScreen> {
  bool _generating = false;
  String? _statusMessage;

  Future<void> _generateWaybill() async {
    setState(() {
      _generating = true;
      _statusMessage = null;
    });

    try {
      final client = ref.read(inventreeClientProvider);
      final result = await client.generateWaybill({});
      setState(() {
        _statusMessage = 'Waybill generated: ${result['job_id'] ?? 'OK'}';
      });
    } catch (e) {
      setState(() {
        _statusMessage = 'Error: $e';
      });
    } finally {
      setState(() => _generating = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = S.of(context);

    return Scaffold(
      appBar: AppBar(title: Text(l10n.waybill)),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.local_shipping, size: 64),
              const SizedBox(height: 24),
              Text(
                'Waybill Generation',
                style: Theme.of(context).textTheme.headlineSmall,
              ),
              const SizedBox(height: 16),
              Text(
                'Generate waybills via the InvenTree Invoice Print plugin.',
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 24),
              if (_generating)
                const CircularProgressIndicator()
              else
                FilledButton.icon(
                  onPressed: _generateWaybill,
                  icon: const Icon(Icons.print),
                  label: const Text('Generate Waybill'),
                ),
              if (_statusMessage != null) ...[
                const SizedBox(height: 16),
                Text(_statusMessage!),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
