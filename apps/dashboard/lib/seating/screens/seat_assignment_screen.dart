import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shinbee_dashboard/shared/l10n/generated/app_localizations.dart';

import '../../app/auth/auth_state.dart';
import '../../app/auth/token_manager.dart';
import '../api/seating_client.dart';
import '../providers/seating_providers.dart';

/// Shows the current user's seat assignment and history.
class SeatAssignmentScreen extends ConsumerWidget {
  const SeatAssignmentScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = S.of(context);
    final assignmentAsync = ref.watch(myAssignmentProvider);
    final historyAsync = ref.watch(assignmentHistoryProvider);
    final authState = ref.watch(tokenManagerProvider);
    final email = authState is Authenticated ? authState.email : '';

    return Scaffold(
      appBar: AppBar(title: Text(l10n.seatMySeat)),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // Current assignment
          Text(l10n.seatCurrentAssignment,
              style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          assignmentAsync.when(
            data: (assignment) {
              if (assignment == null) {
                return Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Text(l10n.seatNoCurrentAssignment),
                  ),
                );
              }
              return Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          const Icon(Icons.check_circle,
                              color: Colors.green, size: 20),
                          const SizedBox(width: 8),
                          Text(
                            'Ext ${assignment.employeeExtension}',
                            style: Theme.of(context).textTheme.titleLarge,
                          ),
                        ],
                      ),
                      const SizedBox(height: 8),
                      Text('${l10n.seatCheckedInAt}: ${assignment.checkedInAt}'),
                      const SizedBox(height: 16),
                      SizedBox(
                        width: double.infinity,
                        child: OutlinedButton.icon(
                          onPressed: () async {
                            final client = ref.read(seatingClientProvider);
                            try {
                              await client.checkOut(deskId: assignment.deskId);
                              ref.invalidate(myAssignmentProvider);
                              ref.invalidate(assignmentHistoryProvider);
                            } catch (e) {
                              if (context.mounted) {
                                ScaffoldMessenger.of(context).showSnackBar(
                                  SnackBar(content: Text(e.toString())),
                                );
                              }
                            }
                          },
                          icon: const Icon(Icons.logout),
                          label: Text(l10n.seatCheckOut),
                        ),
                      ),
                    ],
                  ),
                ),
              );
            },
            loading: () =>
                const Center(child: CircularProgressIndicator()),
            error: (e, _) => Text(e.toString()),
          ),
          const SizedBox(height: 24),
          // History
          Text(l10n.seatHistory,
              style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          historyAsync.when(
            data: (history) {
              if (history.isEmpty) {
                return Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Text(l10n.seatNoHistory),
                  ),
                );
              }
              return Column(
                children: history.map((a) {
                  return Card(
                    child: ListTile(
                      leading: Icon(
                        a.isActive ? Icons.login : Icons.logout,
                        color: a.isActive ? Colors.green : Colors.grey,
                      ),
                      title: Text('Ext ${a.employeeExtension}'),
                      subtitle: Text(a.isActive
                          ? '${l10n.seatCheckedInAt}: ${a.checkedInAt}'
                          : '${a.checkedInAt} - ${a.checkedOutAt}'),
                    ),
                  );
                }).toList(),
              );
            },
            loading: () =>
                const Center(child: CircularProgressIndicator()),
            error: (e, _) => Text(e.toString()),
          ),
        ],
      ),
    );
  }
}
