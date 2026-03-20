import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shinbee_dashboard/shared/l10n/generated/app_localizations.dart';

import '../providers/layout_provider.dart';

class CustomizeScreen extends ConsumerWidget {
  const CustomizeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = S.of(context);
    final layout = ref.watch(layoutProvider);
    final notifier = ref.read(layoutProvider.notifier);

    final allWidgets = [
      ('inventory', l10n.tabInventory),
      ('tasks', l10n.tabTasks),
      ('wiki', l10n.tabWiki),
      ('voice_request', l10n.voiceRequest),
      ('call_request', l10n.callRequest),
      ('rakuten', l10n.rakutenKeyManagement),
      ('picking_list', l10n.pickingList),
      ('fax_review', l10n.faxReview),
    ];

    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.customizeDashboard),
        actions: [
          TextButton(
            onPressed: () => notifier.resetToDefaults(),
            child: Text(l10n.resetDefaults),
          ),
        ],
      ),
      body: ReorderableListView.builder(
        padding: const EdgeInsets.all(16),
        itemCount: layout.widgetOrder.length,
        onReorder: (oldIndex, newIndex) {
          notifier.reorder(oldIndex, newIndex);
        },
        itemBuilder: (context, index) {
          final id = layout.widgetOrder[index];
          final label = allWidgets
              .firstWhere((w) => w.$1 == id, orElse: () => (id, id))
              .$2;
          final isVisible = layout.visibleWidgets.contains(id);

          return ListTile(
            key: ValueKey(id),
            leading: const Icon(Icons.drag_handle),
            title: Text(label),
            trailing: Switch(
              value: isVisible,
              onChanged: (value) => notifier.toggleWidget(id, value),
            ),
          );
        },
      ),
    );
  }
}
