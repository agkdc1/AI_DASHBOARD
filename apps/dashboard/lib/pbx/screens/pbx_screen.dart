import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_tabler_icons/flutter_tabler_icons.dart';
import 'package:shinbee_dashboard/shared/l10n/generated/app_localizations.dart';

import '../api/pbx_client.dart';
import '../providers/pbx_providers.dart';

/// PBX management dashboard with tabs: Extensions, Day/Night, Routes, Status.
class PbxScreen extends ConsumerStatefulWidget {
  const PbxScreen({super.key});

  @override
  ConsumerState<PbxScreen> createState() => _PbxScreenState();
}

class _PbxScreenState extends ConsumerState<PbxScreen>
    with TickerProviderStateMixin {
  late final TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 4, vsync: this);
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
        title: Text(l10n.pbxManagement),
        bottom: TabBar(
          controller: _tabController,
          isScrollable: true,
          tabs: [
            Tab(text: l10n.pbxExtensions, icon: const Icon(TablerIcons.phone)),
            Tab(
                text: l10n.pbxDayNight,
                icon: const Icon(TablerIcons.sun_moon)),
            Tab(
                text: l10n.pbxRoutes,
                icon: const Icon(TablerIcons.route)),
            Tab(
                text: l10n.pbxStatus,
                icon: const Icon(TablerIcons.activity)),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabController,
        children: const [
          _ExtensionsTab(),
          _DayNightTab(),
          _RoutesTab(),
          _StatusTab(),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Extensions Tab
// ---------------------------------------------------------------------------

class _ExtensionsTab extends ConsumerWidget {
  const _ExtensionsTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = S.of(context);
    final extensions = ref.watch(pbxExtensionsProvider);

    return extensions.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(child: Text('${l10n.error}: $e')),
      data: (exts) => Scaffold(
        body: exts.isEmpty
            ? Center(child: Text(l10n.noResults))
            : ListView.builder(
                itemCount: exts.length,
                itemBuilder: (context, index) {
                  final ext = exts[index];
                  return ListTile(
                    leading: CircleAvatar(child: Text(ext['extension'] ?? '')),
                    title: Text(ext['name'] ?? ext['extension'] ?? ''),
                    subtitle: Text(
                        '${l10n.phoneExtension}: ${ext['extension']}'),
                    trailing: PopupMenuButton<String>(
                      onSelected: (action) async {
                        if (action == 'delete') {
                          final confirm = await showDialog<bool>(
                            context: context,
                            builder: (ctx) => AlertDialog(
                              title: Text(l10n.delete),
                              content: Text(l10n.confirmDelete),
                              actions: [
                                TextButton(
                                  onPressed: () => Navigator.pop(ctx, false),
                                  child: Text(l10n.cancel),
                                ),
                                TextButton(
                                  onPressed: () => Navigator.pop(ctx, true),
                                  child: Text(l10n.delete),
                                ),
                              ],
                            ),
                          );
                          if (confirm == true) {
                            final client = ref.read(pbxClientProvider);
                            await client
                                .deleteExtension(ext['extension'] ?? '');
                            ref.invalidate(pbxExtensionsProvider);
                          }
                        }
                      },
                      itemBuilder: (ctx) => [
                        PopupMenuItem(
                          value: 'delete',
                          child: Text(l10n.delete),
                        ),
                      ],
                    ),
                  );
                },
              ),
        floatingActionButton: FloatingActionButton(
          onPressed: () => _showAddExtensionDialog(context, ref),
          child: const Icon(Icons.add),
        ),
      ),
    );
  }

  void _showAddExtensionDialog(BuildContext context, WidgetRef ref) {
    final l10n = S.of(context);
    final extCtrl = TextEditingController();
    final nameCtrl = TextEditingController();
    final pwCtrl = TextEditingController();

    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(l10n.pbxAddExtension),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: extCtrl,
              decoration: InputDecoration(labelText: l10n.phoneExtension),
              keyboardType: TextInputType.number,
            ),
            TextField(
              controller: nameCtrl,
              decoration: InputDecoration(labelText: l10n.phoneName),
            ),
            TextField(
              controller: pwCtrl,
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
          TextButton(
            onPressed: () async {
              if (extCtrl.text.isEmpty || nameCtrl.text.isEmpty) return;
              Navigator.pop(ctx);
              final client = ref.read(pbxClientProvider);
              await client.createExtension(
                extension: extCtrl.text,
                name: nameCtrl.text,
                password: pwCtrl.text.isEmpty ? null : pwCtrl.text,
              );
              ref.invalidate(pbxExtensionsProvider);
            },
            child: Text(l10n.save),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Day/Night Tab
// ---------------------------------------------------------------------------

class _DayNightTab extends ConsumerWidget {
  const _DayNightTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = S.of(context);
    final modes = ref.watch(pbxDayNightProvider);

    return modes.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(child: Text('${l10n.error}: $e')),
      data: (modeList) => ListView.builder(
        itemCount: modeList.length,
        itemBuilder: (context, index) {
          final mode = modeList[index];
          final isNight = mode['current_state'] == 'night';
          return ListTile(
            leading: Icon(
              isNight ? TablerIcons.moon : TablerIcons.sun,
              color: isNight ? Colors.indigo : Colors.amber,
            ),
            title: Text(mode['name'] ?? 'Mode ${mode['id']}'),
            subtitle: Text(isNight ? l10n.pbxNightMode : l10n.pbxDayMode),
            trailing: Switch(
              value: isNight,
              onChanged: (value) async {
                final client = ref.read(pbxClientProvider);
                await client.toggleDayNight(mode['id'] as int);
                ref.invalidate(pbxDayNightProvider);
              },
            ),
          );
        },
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Routes Tab
// ---------------------------------------------------------------------------

class _RoutesTab extends ConsumerWidget {
  const _RoutesTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = S.of(context);
    final outbound = ref.watch(pbxOutboundRoutesProvider);
    final inbound = ref.watch(pbxInboundRoutesProvider);

    return ListView(
      children: [
        Padding(
          padding: const EdgeInsets.all(16),
          child: Text(l10n.pbxOutboundRoutes,
              style: Theme.of(context).textTheme.titleMedium),
        ),
        outbound.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => ListTile(title: Text('${l10n.error}: $e')),
          data: (routes) => Column(
            children: routes.map((r) {
              final isBlock = r['action'] == 'BLOCK';
              return ListTile(
                leading: Icon(
                  isBlock ? TablerIcons.ban : TablerIcons.arrow_up_right,
                  color: isBlock ? Colors.red : Colors.green,
                ),
                title: Text(r['name'] ?? ''),
                subtitle: Text(r['pattern'] ?? ''),
                trailing: Text(r['trunk'] ?? ''),
              );
            }).toList(),
          ),
        ),
        const Divider(),
        Padding(
          padding: const EdgeInsets.all(16),
          child: Text(l10n.pbxInboundRoutes,
              style: Theme.of(context).textTheme.titleMedium),
        ),
        inbound.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => ListTile(title: Text('${l10n.error}: $e')),
          data: (routes) => Column(
            children: routes.map((r) => ListTile(
              leading: const Icon(TablerIcons.arrow_down_left),
              title: Text(r['did'] ?? ''),
              subtitle: Text(r['description'] ?? ''),
              trailing: Text(r['destination'] ?? ''),
            )).toList(),
          ),
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// Status Tab
// ---------------------------------------------------------------------------

class _StatusTab extends ConsumerWidget {
  const _StatusTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = S.of(context);
    final status = ref.watch(pbxStatusProvider);

    return status.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(child: Text('${l10n.error}: $e')),
      data: (s) => ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(l10n.pbxStatus,
                      style: Theme.of(context).textTheme.titleLarge),
                  const SizedBox(height: 16),
                  _statusRow(l10n.pbxUptime, s['uptime']?.toString() ?? '-'),
                  _statusRow(
                      l10n.pbxChannels, s['channels']?.toString() ?? '-'),
                  _statusRow(l10n.pbxEndpointsRegistered,
                      '${s['endpoints_registered'] ?? '-'}'),
                  _statusRow(l10n.pbxEndpointsTotal,
                      '${s['endpoints_total'] ?? '-'}'),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          ElevatedButton.icon(
            onPressed: () async {
              final client = ref.read(pbxClientProvider);
              await client.reload();
              ref.invalidate(pbxStatusProvider);
              if (context.mounted) {
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(content: Text(l10n.pbxReloaded)),
                );
              }
            },
            icon: const Icon(TablerIcons.refresh),
            label: Text(l10n.pbxReload),
          ),
        ],
      ),
    );
  }

  Widget _statusRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 180,
            child: Text(label, style: const TextStyle(fontWeight: FontWeight.bold)),
          ),
          Expanded(child: Text(value)),
        ],
      ),
    );
  }
}
