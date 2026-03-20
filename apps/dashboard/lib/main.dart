import 'package:adaptive_theme/adaptive_theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_web_plugins/url_strategy.dart';
import 'package:shinbee_dashboard/shared/l10n/generated/app_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app/router.dart';
import 'app/theme.dart';

/// User-selected locale override. null = follow system.
class LocaleNotifier extends StateNotifier<Locale?> {
  LocaleNotifier() : super(const Locale('ja')); // Default: Japanese

  void setLocale(Locale? locale) => state = locale;
}

final localeNotifierProvider =
    StateNotifierProvider<LocaleNotifier, Locale?>(
  (ref) => LocaleNotifier(),
);

void main() async {
  usePathUrlStrategy();
  WidgetsFlutterBinding.ensureInitialized();
  final savedThemeMode = await AdaptiveTheme.getThemeMode();
  runApp(
    ProviderScope(child: ShinbeeApp(savedThemeMode: savedThemeMode)),
  );
}

class ShinbeeApp extends ConsumerWidget {
  const ShinbeeApp({this.savedThemeMode, super.key});

  final AdaptiveThemeMode? savedThemeMode;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(routerProvider);
    final localeOverride = ref.watch(localeNotifierProvider);

    return AdaptiveTheme(
      light: ShinbeeTheme.light,
      dark: ShinbeeTheme.dark,
      initial: savedThemeMode ?? AdaptiveThemeMode.system,
      builder: (theme, darkTheme) => MaterialApp.router(
        title: 'シンビジャパン',
        theme: theme,
        darkTheme: darkTheme,
        routerConfig: router,
        locale: localeOverride,
        localizationsDelegates: S.localizationsDelegates,
        supportedLocales: const [
          Locale('ja'), // Japanese (primary)
          Locale('ko'), // Korean (secondary)
          Locale('en'), // English
        ],
        debugShowCheckedModeBanner: false,
      ),
    );
  }
}
