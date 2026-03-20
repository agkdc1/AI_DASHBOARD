import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:shinbee_dashboard/shared/l10n/generated/app_localizations.dart';

import '../api/staff_client.dart';
import '../models/staff.dart';
import '../providers/permission_provider.dart';
import '../providers/staff_providers.dart';

class StaffDetailScreen extends ConsumerStatefulWidget {
  const StaffDetailScreen({super.key, required this.email});
  final String email;

  @override
  ConsumerState<StaffDetailScreen> createState() => _StaffDetailScreenState();
}

class _StaffDetailScreenState extends ConsumerState<StaffDetailScreen> {
  String? _selectedRole;
  Set<String> _denied = {};
  bool _saving = false;
  bool _dirty = false;

  @override
  Widget build(BuildContext context) {
    final l10n = S.of(context);
    final locale = Localizations.localeOf(context).languageCode;
    final staffAsync = ref.watch(staffDetailProvider(widget.email));
    final permsAsync = ref.watch(permissionsDefProvider);

    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.staffDetail),
        actions: [
          if (staffAsync.hasValue && staffAsync.value!.role != 'superuser')
            IconButton(
              icon: const Icon(Icons.delete, color: Colors.red),
              onPressed: () => _confirmDelete(context, l10n),
            ),
        ],
      ),
      body: staffAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (err, _) => Center(child: Text('${l10n.error}: $err')),
        data: (staff) {
          // Initialize local state from server data
          _selectedRole ??= staff.role;
          if (!_dirty) {
            _denied = Set.from(staff.deniedPermissions);
          }

          return permsAsync.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (err, _) => Center(child: Text('${l10n.error}: $err')),
            data: (permDefs) => _buildBody(
              context, l10n, locale, staff, permDefs,
            ),
          );
        },
      ),
    );
  }

  Widget _buildBody(
    BuildContext context,
    S l10n,
    String locale,
    StaffMember staff,
    List<PermissionDef> permDefs,
  ) {
    final guaranteed =
        roleGuaranteed[_selectedRole ?? staff.role] ?? const [];
    final isSuperuser = staff.role == 'superuser';

    // Group permissions by category
    final grouped = <String, List<PermissionDef>>{};
    for (final p in permDefs) {
      grouped.putIfAbsent(p.category, () => []).add(p);
    }

    return Column(
      children: [
        Expanded(
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              // Header
              Center(
                child: CircleAvatar(
                  radius: 40,
                  backgroundImage: staff.photoUrl != null
                      ? NetworkImage(staff.photoUrl!)
                      : null,
                  child: staff.photoUrl == null
                      ? Text(
                          staff.displayName.isNotEmpty
                              ? staff.displayName[0].toUpperCase()
                              : '?',
                          style: const TextStyle(fontSize: 32),
                        )
                      : null,
                ),
              ),
              const SizedBox(height: 8),
              Center(
                child: Text(
                  staff.displayName,
                  style: Theme.of(context).textTheme.titleLarge,
                ),
              ),
              Center(
                child: Text(
                  staff.email,
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ),
              const SizedBox(height: 24),

              // Role dropdown
              if (!isSuperuser) ...[
                Text(l10n.staffRole,
                    style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 8),
                DropdownButtonFormField<String>(
                  value: _selectedRole ?? staff.role,
                  items: const [
                    DropdownMenuItem(value: 'staff', child: Text('Staff')),
                    DropdownMenuItem(
                        value: 'phone_admin', child: Text('Phone Admin')),
                    DropdownMenuItem(value: 'admin', child: Text('Admin')),
                  ],
                  onChanged: (v) {
                    setState(() {
                      _selectedRole = v;
                      _dirty = true;
                      // Remove deny rules for newly guaranteed perms
                      final newGuaranteed =
                          roleGuaranteed[v] ?? const [];
                      _denied.removeAll(newGuaranteed);
                    });
                  },
                ),
                const SizedBox(height: 24),
              ],

              // Permissions section
              Text(l10n.staffPermissions,
                  style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 4),
              Text(
                l10n.staffPermissionsHint,
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: Colors.grey,
                    ),
              ),
              const SizedBox(height: 12),

              if (isSuperuser)
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Text(l10n.staffSuperuserAllAccess),
                  ),
                )
              else
                ...grouped.entries.map((entry) {
                  final categoryLabel = _categoryLabel(entry.key, locale);
                  return Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Padding(
                        padding: const EdgeInsets.symmetric(vertical: 8),
                        child: Text(
                          categoryLabel,
                          style: Theme.of(context)
                              .textTheme
                              .labelLarge
                              ?.copyWith(
                                color: Theme.of(context).colorScheme.primary,
                              ),
                        ),
                      ),
                      ...entry.value.map((perm) {
                        final isGuaranteed =
                            guaranteed.contains(perm.id);
                        final isAllowed = !_denied.contains(perm.id);
                        return SwitchListTile(
                          title: Text(perm.label(locale)),
                          subtitle: isGuaranteed
                              ? Text(
                                  l10n.staffGuaranteedByRole,
                                  style: const TextStyle(
                                    fontSize: 12,
                                    fontStyle: FontStyle.italic,
                                  ),
                                )
                              : null,
                          value: isGuaranteed || isAllowed,
                          onChanged: isGuaranteed
                              ? null
                              : (val) {
                                  setState(() {
                                    _dirty = true;
                                    if (val) {
                                      _denied.remove(perm.id);
                                    } else {
                                      _denied.add(perm.id);
                                    }
                                  });
                                },
                        );
                      }),
                    ],
                  );
                }),
            ],
          ),
        ),

        // Save button
        if (!isSuperuser)
          Padding(
            padding: const EdgeInsets.all(16),
            child: SizedBox(
              width: double.infinity,
              child: FilledButton(
                onPressed: _saving ? null : () => _save(context, l10n, staff),
                child: _saving
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : Text(l10n.save),
              ),
            ),
          ),
      ],
    );
  }

  Future<void> _save(BuildContext context, S l10n, StaffMember staff) async {
    setState(() => _saving = true);
    try {
      final client = ref.read(staffClientProvider);

      // Update role if changed
      if (_selectedRole != null && _selectedRole != staff.role) {
        await client.updateStaff(staff.email, role: _selectedRole);
      }

      // Update deny rules
      await client.setDenyRules(staff.email, _denied.toList());

      // Refresh
      ref.invalidate(staffDetailProvider(widget.email));
      ref.invalidate(staffListProvider);
      _dirty = false;

      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(l10n.save)),
        );
      }
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('${l10n.error}: $e')),
        );
      }
    } finally {
      setState(() => _saving = false);
    }
  }

  Future<void> _confirmDelete(BuildContext context, S l10n) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(l10n.staffDeleteConfirm),
        content: Text(widget.email),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: Text(l10n.cancel),
          ),
          TextButton(
            style: TextButton.styleFrom(foregroundColor: Colors.red),
            onPressed: () => Navigator.pop(ctx, true),
            child: Text(l10n.delete),
          ),
        ],
      ),
    );

    if (confirmed == true && context.mounted) {
      try {
        final client = ref.read(staffClientProvider);
        await client.deleteStaff(widget.email);
        ref.invalidate(staffListProvider);
        if (context.mounted) context.pop();
      } catch (e) {
        if (context.mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('${l10n.error}: $e')),
          );
        }
      }
    }
  }

  String _categoryLabel(String category, String locale) {
    const labels = {
      'inventory': {'en': 'Inventory', 'ja': '在庫管理', 'ko': '재고관리'},
      'orders': {'en': 'Orders', 'ja': '受注管理', 'ko': '주문관리'},
      'tasks': {'en': 'Tasks', 'ja': 'タスク', 'ko': '태스크'},
      'wiki': {'en': 'Wiki', 'ja': 'Wiki', 'ko': 'Wiki'},
      'features': {'en': 'Features', 'ja': '機能', 'ko': '기능'},
      'admin': {'en': 'Admin', 'ja': '管理', 'ko': '관리'},
    };
    return labels[category]?[locale] ?? labels[category]?['en'] ?? category;
  }
}
