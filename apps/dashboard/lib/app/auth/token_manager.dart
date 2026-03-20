import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'auth_state.dart';
import 'platform_redirect_stub.dart'
    if (dart.library.html) 'platform_redirect_web.dart';
import 'sso_config.dart';
import 'test_auth_config.dart';

const _kEmail = 'user_email';
const _kDisplayName = 'user_display_name';
const _kPhotoUrl = 'user_photo_url';

/// On web, use localStorage without encryption to avoid Web Crypto
/// OperationError issues (key corruption, incognito mode, etc.).
FlutterSecureStorage _createStorage() {
  if (kIsWeb) {
    return const FlutterSecureStorage(
      webOptions: WebOptions(
        dbName: 'shinbee_auth',
        publicKey: 'shinbee_auth_key',
      ),
    );
  }
  return const FlutterSecureStorage();
}

class TokenManager extends StateNotifier<AuthState> {
  TokenManager(this._ref) : super(const AuthState.unauthenticated()) {
    _tryRestoreSession();
  }

  final Ref _ref;
  final _storage = _createStorage();
  final _dio = Dio(BaseOptions(
    extra: kIsWeb ? {'withCredentials': true} : null,
  ));

  Future<void> _tryRestoreSession() async {
    try {
      final email = await _storage.read(key: _kEmail);
      final displayName = await _storage.read(key: _kDisplayName);
      final photoUrl = await _storage.read(key: _kPhotoUrl);

      if (email != null && email.isNotEmpty && displayName != null) {
        // Cached session — verify it's still valid by probing the API
        state = AuthState.authenticated(
          email: email,
          displayName: displayName,
          photoUrl: photoUrl,
        );
      }
    } catch (_) {
      try {
        await _storage.deleteAll();
      } catch (_) {}
    }
  }

  /// Check if the Authentik forward-auth session is valid.
  /// Calls AI assistant /auth/session which validates the Authentik proxy
  /// cookie server-side — no InvenTree dependency.
  Future<bool> checkSession() async {
    try {
      // Use same-origin path — flutter-dashboard nginx proxies to AI assistant.
      // This avoids cross-origin cookie issues (SameSite=Lax blocks XHR).
      final baseUrl = kIsWeb ? '' : SsoConfig.aiAssistantBaseUrl;
      final resp = await _dio.get(
        '$baseUrl/auth/session',
        options: Options(
          followRedirects: false,
          validateStatus: (s) => s != null && s < 400,
        ),
      );
      if (resp.statusCode == 200 && resp.data is Map) {
        final data = resp.data as Map<String, dynamic>;
        final email = (data['email'] as String? ?? '').trim();
        final displayName = (data['display_name'] as String? ?? '').trim();

        if (email.isEmpty) return false;

        await Future.wait([
          _storage.write(key: _kEmail, value: email),
          _storage.write(key: _kDisplayName, value: displayName),
        ]);

        state = AuthState.authenticated(
          email: email,
          displayName: displayName,
        );
        return true;
      }
    } catch (_) {}
    return false;
  }

  /// Redirect to Authentik forward auth login.
  /// After login, Authentik redirects back to app.your-domain.com
  /// with the proxy cookie set on .your-domain.com.
  void redirectToLogin() {
    final redirectUrl = Uri.encodeComponent('https://app.your-domain.com/');
    final loginUrl =
        'https://auth.your-domain.com/outpost.goauthentik.io/start?rd=$redirectUrl';
    if (kIsWeb) {
      performWebRedirect(loginUrl);
    }
  }

  /// Legacy signIn — redirects to Authentik login.
  Future<void> signIn() async {
    state = const AuthState.authenticating();
    redirectToLogin();
  }

  Future<void> signOut() async {
    try {
      await _storage.deleteAll();
    } catch (_) {}
    state = const AuthState.unauthenticated();
    // Redirect to Authentik logout to clear the session cookie
    if (kIsWeb) {
      performWebRedirect(
          'https://auth.your-domain.com/application/o/flutter-app/end-session/');
    }
  }

  /// Sign in using username/password (test mode only).
  Future<void> signInWithCredentials(String username, String password) async {
    if (!TestAuthConfig.isTestMode) return;

    state = const AuthState.authenticating();

    try {
      final baseUrl = TestAuthConfig.testApiUrl;

      final resp = await _dio.get(
        '$baseUrl/api/user/token/',
        options: Options(headers: {
          'Authorization':
              'Basic ${base64Encode(utf8.encode('$username:$password'))}',
        }),
      );

      final token = resp.data?['token'];
      if (token is! String) {
        state = const AuthState.error('No token in response');
        return;
      }

      const email = 'test@your-domain.com';
      const displayName = 'Test User';

      await Future.wait([
        _storage.write(key: _kEmail, value: email),
        _storage.write(key: _kDisplayName, value: displayName),
      ]);

      state = const AuthState.authenticated(
        email: email,
        displayName: displayName,
      );
    } catch (e) {
      state = AuthState.error(e.toString());
    }
  }

  Future<void> _autoProvisionPhone(String email, String displayName) async {
    try {
      await _dio.post(
        '${SsoConfig.aiAssistantBaseUrl}/phone/auto-provision',
        data: {'email': email, 'display_name': displayName},
      );
    } catch (_) {}
  }
}

final tokenManagerProvider =
    StateNotifierProvider<TokenManager, AuthState>(
  (ref) => TokenManager(ref),
);
