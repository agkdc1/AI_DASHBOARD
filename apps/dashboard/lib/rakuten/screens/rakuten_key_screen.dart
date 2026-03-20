import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shinbee_dashboard/shared/l10n/generated/app_localizations.dart';

import '../providers/rakuten_providers.dart';

class RakutenKeyScreen extends ConsumerStatefulWidget {
  const RakutenKeyScreen({super.key});

  @override
  ConsumerState<RakutenKeyScreen> createState() => _RakutenKeyScreenState();
}

class _RakutenKeyScreenState extends ConsumerState<RakutenKeyScreen> {
  final _serviceSecretCtrl = TextEditingController();
  final _licenseKeyCtrl = TextEditingController();
  bool _submitting = false;

  @override
  void dispose() {
    _serviceSecretCtrl.dispose();
    _licenseKeyCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = S.of(context);
    final statusAsync = ref.watch(rakutenStatusProvider);

    return Scaffold(
      appBar: AppBar(title: Text(l10n.rakutenKeyManagement)),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // Status card
          statusAsync.when(
            data: (status) => _buildStatusCard(context, l10n, status),
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (e, _) => Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Text('Error: $e'),
              ),
            ),
          ),
          const SizedBox(height: 24),

          // Instructions
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(l10n.rakutenInstructions,
                      style: Theme.of(context).textTheme.titleMedium),
                  const SizedBox(height: 8),
                  Text(l10n.rakutenStep1),
                  Text(l10n.rakutenStep2),
                  Text(l10n.rakutenStep3),
                ],
              ),
            ),
          ),
          const SizedBox(height: 24),

          // Key submission
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(l10n.rakutenSubmitKeys,
                      style: Theme.of(context).textTheme.titleMedium),
                  const SizedBox(height: 16),
                  TextField(
                    controller: _serviceSecretCtrl,
                    decoration: InputDecoration(
                      labelText: 'Service Secret',
                      border: const OutlineInputBorder(),
                    ),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: _licenseKeyCtrl,
                    decoration: InputDecoration(
                      labelText: 'License Key',
                      border: const OutlineInputBorder(),
                    ),
                  ),
                  const SizedBox(height: 16),
                  SizedBox(
                    width: double.infinity,
                    child: FilledButton(
                      onPressed: _submitting ? null : _submitKeys,
                      child: _submitting
                          ? const SizedBox(
                              height: 20,
                              width: 20,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : Text(l10n.rakutenSubmit),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildStatusCard(BuildContext context, S l10n, Map<String, dynamic> status) {
    final ageDays = status['age_days'] as int?;
    final daysUntilDeadline = status['days_until_deadline'] as int?;
    final renewedAt = status['renewed_at'] as String?;

    Color statusColor;
    String statusText;
    if (ageDays == null) {
      statusColor = Colors.grey;
      statusText = l10n.rakutenStatusUnknown;
    } else if (daysUntilDeadline != null && daysUntilDeadline <= 0) {
      statusColor = Colors.red;
      statusText = l10n.rakutenStatusExpired;
    } else if (ageDays >= 80) {
      statusColor = Colors.orange;
      statusText = l10n.rakutenStatusWarning;
    } else {
      statusColor = Colors.green;
      statusText = l10n.rakutenStatusOk;
    }

    return Card(
      color: statusColor.withOpacity(0.1),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.vpn_key, color: statusColor),
                const SizedBox(width: 8),
                Text(statusText,
                    style: Theme.of(context)
                        .textTheme
                        .titleMedium
                        ?.copyWith(color: statusColor)),
              ],
            ),
            if (renewedAt != null) ...[
              const SizedBox(height: 8),
              Text('${l10n.rakutenRenewedAt}: ${renewedAt.substring(0, 10)}'),
            ],
            if (ageDays != null)
              Text('${l10n.rakutenAgeDays}: $ageDays'),
            if (daysUntilDeadline != null)
              Text('${l10n.rakutenDaysRemaining}: $daysUntilDeadline'),
          ],
        ),
      ),
    );
  }

  Future<void> _submitKeys() async {
    if (_serviceSecretCtrl.text.isEmpty || _licenseKeyCtrl.text.isEmpty) return;

    setState(() => _submitting = true);
    try {
      await ref.read(rakutenSubmitProvider((
        serviceSecret: _serviceSecretCtrl.text,
        licenseKey: _licenseKeyCtrl.text,
      )).future);
      ref.invalidate(rakutenStatusProvider);
      _serviceSecretCtrl.clear();
      _licenseKeyCtrl.clear();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Keys updated successfully')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }
}
