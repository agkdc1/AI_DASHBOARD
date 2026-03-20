import 'package:adaptive_theme/adaptive_theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:shinbee_dashboard/shared/l10n/generated/app_localizations.dart';

import '../main.dart';
import 'auth/auth_state.dart';
import 'auth/token_manager.dart';

final _localeOptions = <Locale, String>{
  Locale('ja'): '日本語',
  Locale('ko'): '한국어',
  Locale('en'): 'English',
};

class SettingsScreen extends ConsumerWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = S.of(context);
    final authState = ref.watch(tokenManagerProvider);
    final theme = Theme.of(context);
    final currentLocale = ref.watch(localeNotifierProvider) ??
        Localizations.localeOf(context);

    return Scaffold(
      appBar: AppBar(title: Text(l10n.settingsTitle)),
      body: ListView(
        children: [
          if (authState is Authenticated) ...[
            ListTile(
              leading: CircleAvatar(
                backgroundImage: authState.photoUrl != null
                    ? NetworkImage(authState.photoUrl!)
                    : null,
                child: authState.photoUrl == null
                    ? Text(authState.displayName[0].toUpperCase())
                    : null,
              ),
              title: Text(authState.displayName),
              subtitle: Text(authState.email),
            ),
            const Divider(),
          ],
          ListTile(
            leading: const Icon(Icons.language),
            title: Text(l10n.settingsLanguage),
            trailing: SegmentedButton<Locale>(
              segments: _localeOptions.entries
                  .map((e) => ButtonSegment(
                        value: e.key,
                        label: Text(e.value),
                      ))
                  .toList(),
              selected: {currentLocale},
              onSelectionChanged: (locales) {
                ref
                    .read(localeNotifierProvider.notifier)
                    .setLocale(locales.first);
              },
            ),
          ),
          ListTile(
            leading: const Icon(Icons.palette),
            title: Text(l10n.settingsTheme),
            trailing: SegmentedButton<AdaptiveThemeMode>(
              segments: [
                ButtonSegment(
                  value: AdaptiveThemeMode.system,
                  label: Text(l10n.themeSystem),
                ),
                ButtonSegment(
                  value: AdaptiveThemeMode.light,
                  label: Text(l10n.themeLight),
                ),
                ButtonSegment(
                  value: AdaptiveThemeMode.dark,
                  label: Text(l10n.themeDark),
                ),
              ],
              selected: {AdaptiveTheme.of(context).mode},
              onSelectionChanged: (modes) {
                final mode = modes.first;
                switch (mode) {
                  case AdaptiveThemeMode.system:
                    AdaptiveTheme.of(context).setSystem();
                  case AdaptiveThemeMode.light:
                    AdaptiveTheme.of(context).setLight();
                  case AdaptiveThemeMode.dark:
                    AdaptiveTheme.of(context).setDark();
                }
              },
            ),
          ),
          ListTile(
            leading: const Icon(Icons.phone),
            title: Text(l10n.phoneManagement),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => context.go('/settings/phone'),
          ),
          ListTile(
            leading: const Icon(Icons.vpn_key),
            title: Text(l10n.rakutenKeyManagement),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => context.go('/settings/rakuten'),
          ),
          ListTile(
            leading: const Icon(Icons.settings_phone),
            title: Text(l10n.pbxManagement),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => context.go('/settings/pbx'),
          ),
          ListTile(
            leading: const Icon(Icons.info_outline),
            title: Text(l10n.settingsAbout),
            subtitle: const Text('シンビジャパン ダッシュボード v1.0.0'),
          ),
          const Divider(),
          ListTile(
            leading: Icon(Icons.logout, color: theme.colorScheme.error),
            title: Text(
              l10n.logout,
              style: TextStyle(color: theme.colorScheme.error),
            ),
            onTap: () => ref.read(tokenManagerProvider.notifier).signOut(),
          ),
        ],
      ),
    );
  }
}
