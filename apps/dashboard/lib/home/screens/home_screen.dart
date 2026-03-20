import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_tabler_icons/flutter_tabler_icons.dart';
import 'package:go_router/go_router.dart';
import 'package:shinbee_dashboard/shared/l10n/generated/app_localizations.dart';

import '../../staff/providers/permission_provider.dart';
import '../providers/layout_provider.dart';

class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = S.of(context);
    final layout = ref.watch(layoutProvider);
    final theme = Theme.of(context);
    final permsAsync = ref.watch(myPermissionsProvider);

    final allCards = <_ModeCard>[
      _ModeCard(
        id: 'seating',
        icon: TablerIcons.armchair,
        label: l10n.seatManagement,
        route: '/home/seating',
        color: Colors.brown,
        requiredPermission: 'seating.checkin',
      ),
      _ModeCard(
        id: 'inventory',
        icon: TablerIcons.packages,
        label: l10n.tabInventory,
        route: '/inventory',
        color: Colors.blue,
      ),
      _ModeCard(
        id: 'tasks',
        icon: TablerIcons.checklist,
        label: l10n.tabTasks,
        route: '/tasks',
        color: Colors.orange,
      ),
      _ModeCard(
        id: 'wiki',
        icon: TablerIcons.notebook,
        label: l10n.tabWiki,
        route: '/wiki',
        color: Colors.green,
      ),
      _ModeCard(
        id: 'voice_request',
        icon: TablerIcons.microphone,
        label: l10n.voiceRequest,
        route: '/home/voice-request',
        color: Colors.purple,
        requiredPermission: 'voice_request.access',
      ),
      _ModeCard(
        id: 'call_request',
        icon: TablerIcons.phone_call,
        label: l10n.callRequest,
        route: '/home/call-request',
        color: Colors.red,
        requiredPermission: 'call_request.access',
      ),
      _ModeCard(
        id: 'rakuten',
        icon: TablerIcons.key,
        label: l10n.rakutenKeyManagement,
        route: '/settings/rakuten',
        color: Colors.teal,
        requiredPermission: 'rakuten.manage',
      ),
      _ModeCard(
        id: 'picking_list',
        icon: TablerIcons.clipboard_check,
        label: l10n.pickingList,
        route: '/home/picking',
        color: Colors.indigo,
        requiredPermission: 'picking.access',
      ),
      _ModeCard(
        id: 'pbx',
        icon: TablerIcons.phone_plus,
        label: l10n.pbxManagement,
        route: '/settings/pbx',
        color: Colors.cyan,
        requiredPermission: 'phone.admin',
      ),
      _ModeCard(
        id: 'staff',
        icon: TablerIcons.users_group,
        label: l10n.staffManagement,
        route: '/home/staff',
        color: Colors.amber,
        requiredPermission: 'staff.manage',
      ),
      _ModeCard(
        id: 'fax_review',
        icon: TablerIcons.file_text,
        label: l10n.faxReview,
        route: '/home/fax-review',
        color: Colors.teal,
        requiredPermission: 'fax_review.access',
      ),
    ];

    // Filter by layout visibility
    final visibleCards = layout.widgetOrder
        .where((id) => layout.visibleWidgets.contains(id))
        .map((id) => allCards.firstWhere(
              (c) => c.id == id,
              orElse: () => allCards.first,
            ))
        .where((c) => allCards.contains(c))
        .toList();

    // Add any cards not in widgetOrder yet
    for (final card in allCards) {
      if (!visibleCards.contains(card) && layout.visibleWidgets.contains(card.id)) {
        visibleCards.add(card);
      }
    }

    // Filter by permissions (hide cards the user is denied)
    final filteredCards = permsAsync.when(
      data: (profile) {
        // If IAM unavailable or user not registered, show all (default allow)
        if (!profile.registered || profile.allPermissions.isEmpty) {
          return visibleCards;
        }
        return visibleCards.where((card) {
          if (card.requiredPermission == null) return true;
          return profile.isAllowed(card.requiredPermission!);
        }).toList();
      },
      loading: () => visibleCards, // Show all while loading
      error: (_, __) => visibleCards, // Show all on error
    );

    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.appTitle),
        actions: [
          IconButton(
            icon: const Icon(TablerIcons.layout_dashboard),
            onPressed: () => context.go('/home/customize'),
            tooltip: l10n.customizeDashboard,
          ),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: GridView.builder(
          gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: 2,
            crossAxisSpacing: 16,
            mainAxisSpacing: 16,
            childAspectRatio: 1.2,
          ),
          itemCount: filteredCards.length,
          itemBuilder: (context, index) {
            final card = filteredCards[index];
            return _buildCard(context, card, theme);
          },
        ),
      ),
    );
  }

  Widget _buildCard(BuildContext context, _ModeCard card, ThemeData theme) {
    return Card(
      elevation: 2,
      child: InkWell(
        onTap: () => context.go(card.route),
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(card.icon, size: 40, color: card.color),
              const SizedBox(height: 12),
              Text(
                card.label,
                style: theme.textTheme.titleMedium,
                textAlign: TextAlign.center,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ModeCard {
  final String id;
  final IconData icon;
  final String label;
  final String route;
  final Color color;
  final String? requiredPermission;

  const _ModeCard({
    required this.id,
    required this.icon,
    required this.label,
    required this.route,
    required this.color,
    this.requiredPermission,
  });
}
