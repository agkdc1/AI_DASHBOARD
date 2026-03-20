import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shinbee_dashboard/shared/l10n/generated/app_localizations.dart';

import 'auth_state.dart';
import 'test_auth_config.dart';
import 'token_manager.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _usernameController = TextEditingController(text: 'admin');
  final _passwordController = TextEditingController();
  bool _checkingSession = true;

  @override
  void initState() {
    super.initState();
    if (!TestAuthConfig.isTestMode) {
      _checkExistingSession();
    } else {
      _checkingSession = false;
    }
  }

  Future<void> _checkExistingSession() async {
    final ok = await ref.read(tokenManagerProvider.notifier).checkSession();
    if (mounted && !ok) {
      setState(() => _checkingSession = false);
    }
  }

  @override
  void dispose() {
    _usernameController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final authState = ref.watch(tokenManagerProvider);

    if (_checkingSession) {
      return const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      );
    }
    final l10n = S.of(context);
    final theme = Theme.of(context);

    return Scaffold(
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 400),
          child: Padding(
            padding: const EdgeInsets.all(32),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  Icons.inventory_2_outlined,
                  size: 80,
                  color: theme.colorScheme.primary,
                ),
                const SizedBox(height: 24),
                Text(
                  l10n.loginTitle,
                  style: theme.textTheme.headlineMedium,
                ),
                if (TestAuthConfig.isTestMode) ...[
                  const SizedBox(height: 8),
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 12,
                      vertical: 4,
                    ),
                    decoration: BoxDecoration(
                      color: theme.colorScheme.tertiaryContainer,
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Text(
                      'TEST MODE',
                      style: theme.textTheme.labelSmall?.copyWith(
                        color: theme.colorScheme.onTertiaryContainer,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                ],
                const SizedBox(height: 48),
                if (authState is Authenticating)
                  const CircularProgressIndicator()
                else ...[
                  if (TestAuthConfig.isTestMode) ...[
                    // Test mode: username/password fields
                    TextField(
                      controller: _usernameController,
                      decoration: const InputDecoration(
                        labelText: 'Username',
                        border: OutlineInputBorder(),
                        prefixIcon: Icon(Icons.person),
                      ),
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      controller: _passwordController,
                      obscureText: true,
                      decoration: const InputDecoration(
                        labelText: 'Password',
                        border: OutlineInputBorder(),
                        prefixIcon: Icon(Icons.lock),
                      ),
                      onSubmitted: (_) => _signInTest(),
                    ),
                    const SizedBox(height: 16),
                    FilledButton.icon(
                      onPressed: _signInTest,
                      icon: const Icon(Icons.login),
                      label: const Text('Login'),
                      style: FilledButton.styleFrom(
                        minimumSize: const Size(double.infinity, 48),
                      ),
                    ),
                  ] else ...[
                    // Production: Authentik OIDC SSO
                    FilledButton.icon(
                      onPressed: _startLogin,
                      icon: const Icon(Icons.login),
                      label: Text(l10n.loginWithSSO),
                      style: FilledButton.styleFrom(
                        minimumSize: const Size(double.infinity, 48),
                      ),
                    ),
                    const SizedBox(height: 12),
                    Text(
                      l10n.loginDomainHint,
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                      textAlign: TextAlign.center,
                    ),
                  ],
                  if (authState is AuthError) ...[
                    const SizedBox(height: 16),
                    Text(
                      l10n.loginError(authState.message),
                      style: TextStyle(color: theme.colorScheme.error),
                      textAlign: TextAlign.center,
                    ),
                  ],
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }

  void _signInTest() {
    final username = _usernameController.text.trim();
    final password = _passwordController.text;
    if (username.isEmpty || password.isEmpty) return;
    ref.read(tokenManagerProvider.notifier).signInWithCredentials(
          username,
          password,
        );
  }

  void _startLogin() {
    ref.read(tokenManagerProvider.notifier).signIn();
  }
}
