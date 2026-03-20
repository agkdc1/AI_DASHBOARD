import 'package:flutter/material.dart';
import 'package:flutter_tabler_icons/flutter_tabler_icons.dart';
import 'package:go_router/go_router.dart';
import 'package:shinbee_dashboard/shared/l10n/generated/app_localizations.dart';

class BottomNavShell extends StatelessWidget {
  const BottomNavShell({
    required this.navigationShell,
    super.key,
  });

  final StatefulNavigationShell navigationShell;

  @override
  Widget build(BuildContext context) {
    final l10n = S.of(context);

    return Scaffold(
      body: navigationShell,
      bottomNavigationBar: NavigationBar(
        selectedIndex: navigationShell.currentIndex,
        onDestinationSelected: (index) {
          navigationShell.goBranch(
            index,
            initialLocation: index == navigationShell.currentIndex,
          );
        },
        destinations: [
          NavigationDestination(
            icon: const Icon(TablerIcons.home),
            selectedIcon: const Icon(TablerIcons.home),
            label: l10n.tabHome,
          ),
          NavigationDestination(
            icon: const Icon(TablerIcons.packages),
            selectedIcon: const Icon(TablerIcons.packages),
            label: l10n.tabInventory,
          ),
          NavigationDestination(
            icon: const Icon(TablerIcons.checklist),
            selectedIcon: const Icon(TablerIcons.checklist),
            label: l10n.tabTasks,
          ),
          NavigationDestination(
            icon: const Icon(TablerIcons.notebook),
            selectedIcon: const Icon(TablerIcons.notebook),
            label: l10n.tabWiki,
          ),
          NavigationDestination(
            icon: const Icon(TablerIcons.settings),
            selectedIcon: const Icon(TablerIcons.settings),
            label: l10n.tabSettings,
          ),
        ],
      ),
    );
  }
}
