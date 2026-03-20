import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_tabler_icons/flutter_tabler_icons.dart';
import 'package:go_router/go_router.dart';
import 'package:shinbee_dashboard/shared/l10n/generated/app_localizations.dart';

import '../models/staff.dart';
import '../providers/staff_providers.dart';
import '../widgets/add_staff_dialog.dart';

class StaffListScreen extends ConsumerWidget {
  const StaffListScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = S.of(context);
    final staffAsync = ref.watch(staffListProvider);

    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.staffManagement),
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () => _showAddDialog(context, ref),
        child: const Icon(Icons.add),
      ),
      body: staffAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (err, _) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text('${l10n.error}: $err'),
              const SizedBox(height: 8),
              ElevatedButton(
                onPressed: () => ref.invalidate(staffListProvider),
                child: Text(l10n.retry),
              ),
            ],
          ),
        ),
        data: (staff) {
          if (staff.isEmpty) {
            return Center(child: Text(l10n.noResults));
          }
          return ListView.builder(
            itemCount: staff.length,
            itemBuilder: (context, index) =>
                _StaffTile(staff: staff[index]),
          );
        },
      ),
    );
  }

  void _showAddDialog(BuildContext context, WidgetRef ref) {
    showDialog(
      context: context,
      builder: (_) => AddStaffDialog(
        onCreated: () => ref.invalidate(staffListProvider),
        ref: ref,
      ),
    );
  }
}

class _StaffTile extends StatelessWidget {
  const _StaffTile({required this.staff});
  final StaffMember staff;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListTile(
      leading: CircleAvatar(
        backgroundImage:
            staff.photoUrl != null ? NetworkImage(staff.photoUrl!) : null,
        child: staff.photoUrl == null
            ? Text(staff.displayName.isNotEmpty
                ? staff.displayName[0].toUpperCase()
                : '?')
            : null,
      ),
      title: Text(staff.displayName),
      subtitle: Text(staff.email),
      trailing: _RoleBadge(role: staff.role),
      onTap: () => context.go('/home/staff/${Uri.encodeComponent(staff.email)}'),
    );
  }
}

class _RoleBadge extends StatelessWidget {
  const _RoleBadge({required this.role});
  final String role;

  @override
  Widget build(BuildContext context) {
    final (color, label) = switch (role) {
      'superuser' => (Colors.red, 'SUPER'),
      'admin' => (Colors.orange, 'ADMIN'),
      'phone_admin' => (Colors.cyan, 'PHONE'),
      _ => (Colors.grey, 'STAFF'),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha: 0.5)),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: color,
          fontSize: 11,
          fontWeight: FontWeight.bold,
        ),
      ),
    );
  }
}
