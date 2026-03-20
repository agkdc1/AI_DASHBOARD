import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../shared/l10n/generated/app_localizations.dart';
import '../api/phone_client.dart';
import '../models/phone_device.dart';
import '../models/phone_user.dart';
import '../providers/phone_providers.dart';

class PhoneAdminScreen extends ConsumerStatefulWidget {
  const PhoneAdminScreen({super.key});

  @override
  ConsumerState<PhoneAdminScreen> createState() => _PhoneAdminScreenState();
}

class _PhoneAdminScreenState extends ConsumerState<PhoneAdminScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = S.of(context);

    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.phoneManagement),
        bottom: TabBar(
          controller: _tabController,
          tabs: [
            Tab(text: l10n.phoneUsers, icon: const Icon(Icons.people)),
            Tab(text: l10n.phoneDevices, icon: const Icon(Icons.phone_android)),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabController,
        children: const [
          _UsersTab(),
          _DevicesTab(),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () => _showAddUserDialog(context),
        child: const Icon(Icons.person_add),
      ),
    );
  }

  void _showAddUserDialog(BuildContext context) {
    final l10n = S.of(context);
    final extController = TextEditingController();
    final nameController = TextEditingController();
    final passwordController = TextEditingController(text: '1234');

    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(l10n.phoneAddUser),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: extController,
              decoration: InputDecoration(labelText: l10n.phoneExtension),
              keyboardType: TextInputType.number,
            ),
            const SizedBox(height: 8),
            TextField(
              controller: nameController,
              decoration: InputDecoration(labelText: l10n.phoneName),
            ),
            const SizedBox(height: 8),
            TextField(
              controller: passwordController,
              decoration: InputDecoration(labelText: l10n.phonePassword),
              obscureText: true,
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: Text(l10n.cancel),
          ),
          FilledButton(
            onPressed: () async {
              final client = ref.read(phoneClientProvider);
              try {
                await client.createUser(
                  uid: extController.text.trim(),
                  cn: nameController.text.trim(),
                  password: passwordController.text.trim(),
                );
                ref.invalidate(phoneUsersProvider);
                if (ctx.mounted) Navigator.pop(ctx);
              } catch (e) {
                if (ctx.mounted) {
                  ScaffoldMessenger.of(ctx).showSnackBar(
                    SnackBar(content: Text('${l10n.error}: $e')),
                  );
                }
              }
            },
            child: Text(l10n.save),
          ),
        ],
      ),
    );
  }
}

class _UsersTab extends ConsumerWidget {
  const _UsersTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = S.of(context);
    final usersAsync = ref.watch(phoneUsersProvider);

    return usersAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('${l10n.error}: $e'),
            const SizedBox(height: 8),
            FilledButton(
              onPressed: () => ref.invalidate(phoneUsersProvider),
              child: Text(l10n.retry),
            ),
          ],
        ),
      ),
      data: (users) {
        if (users.isEmpty) {
          return Center(child: Text(l10n.noResults));
        }
        return RefreshIndicator(
          onRefresh: () async => ref.invalidate(phoneUsersProvider),
          child: ListView.builder(
            itemCount: users.length,
            itemBuilder: (context, index) {
              final user = users[index];
              return _UserTile(user: user);
            },
          ),
        );
      },
    );
  }
}

class _UserTile extends ConsumerWidget {
  const _UserTile({required this.user});
  final PhoneUser user;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = S.of(context);

    return ListTile(
      leading: CircleAvatar(child: Text(user.uid)),
      title: Text(user.cn),
      subtitle: Text('Ext: ${user.telephoneNumber}'),
      trailing: PopupMenuButton<String>(
        onSelected: (value) async {
          if (value == 'delete') {
            final confirmed = await showDialog<bool>(
              context: context,
              builder: (ctx) => AlertDialog(
                title: Text(l10n.confirmDelete),
                content: Text('${user.cn} (${user.uid})'),
                actions: [
                  TextButton(
                    onPressed: () => Navigator.pop(ctx, false),
                    child: Text(l10n.cancel),
                  ),
                  FilledButton(
                    onPressed: () => Navigator.pop(ctx, true),
                    child: Text(l10n.delete),
                  ),
                ],
              ),
            );
            if (confirmed == true) {
              final client = ref.read(phoneClientProvider);
              await client.deleteUser(user.uid);
              ref.invalidate(phoneUsersProvider);
            }
          }
        },
        itemBuilder: (context) => [
          PopupMenuItem(value: 'delete', child: Text(l10n.delete)),
        ],
      ),
    );
  }
}

class _DevicesTab extends ConsumerWidget {
  const _DevicesTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = S.of(context);
    final devicesAsync = ref.watch(phoneDevicesProvider);

    return devicesAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('${l10n.error}: $e'),
            const SizedBox(height: 8),
            FilledButton(
              onPressed: () => ref.invalidate(phoneDevicesProvider),
              child: Text(l10n.retry),
            ),
          ],
        ),
      ),
      data: (devices) {
        if (devices.isEmpty) {
          return Center(child: Text(l10n.noResults));
        }
        return RefreshIndicator(
          onRefresh: () async => ref.invalidate(phoneDevicesProvider),
          child: ListView.builder(
            itemCount: devices.length,
            itemBuilder: (context, index) {
              final device = devices[index];
              return _DeviceTile(device: device);
            },
          ),
        );
      },
    );
  }
}

class _DeviceTile extends StatelessWidget {
  const _DeviceTile({required this.device});
  final PhoneDevice device;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: Icon(
        device.isFixed ? Icons.phone : Icons.phone_forwarded,
        color: device.isFixed ? Colors.green : Colors.orange,
      ),
      title: Text(device.mac),
      subtitle: Text(device.isFixed
          ? '${device.name} — Ext ${device.extension}'
          : 'Hot-desk'),
      trailing: Chip(
        label: Text(device.type),
        backgroundColor: device.isFixed
            ? Colors.green.withValues(alpha: 0.1)
            : Colors.orange.withValues(alpha: 0.1),
      ),
    );
  }
}
