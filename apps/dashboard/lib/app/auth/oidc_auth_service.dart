import 'dart:convert';
import 'dart:math';

import 'package:crypto/crypto.dart';
import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'sso_config.dart';

/// OIDC authentication result from Authentik.
class OidcTokens {
  const OidcTokens({
    required this.accessToken,
    required this.idToken,
    required this.refreshToken,
    required this.email,
    required this.name,
  });

  final String accessToken;
  final String? idToken;
  final String? refreshToken;
  final String email;
  final String name;
}

/// Handles OIDC Authorization Code + PKCE flow with Authentik.
class OidcAuthService {
  OidcAuthService();

  final _dio = Dio();

  String? _codeVerifier;

  /// Expose verifier for persistence across page redirects.
  String? get codeVerifier => _codeVerifier;

  /// Restore verifier after a page redirect (web).
  void setCodeVerifier(String verifier) {
    _codeVerifier = verifier;
  }

  /// Generates PKCE code verifier and challenge.
  ({String verifier, String challenge}) generatePkce() {
    final random = Random.secure();
    final bytes = List<int>.generate(32, (_) => random.nextInt(256));
    final verifier = base64UrlEncode(bytes).replaceAll('=', '');
    _codeVerifier = verifier;

    final digest = sha256.convert(utf8.encode(verifier));
    final challenge = base64UrlEncode(digest.bytes).replaceAll('=', '');

    return (verifier: verifier, challenge: challenge);
  }

  /// Builds the Authentik authorization URL.
  String buildAuthorizeUrl() {
    final pkce = generatePkce();
    final params = {
      'client_id': SsoConfig.oidcClientId,
      'response_type': 'code',
      'redirect_uri': SsoConfig.oidcRedirectUri,
      'scope': 'openid profile email',
      'code_challenge': pkce.challenge,
      'code_challenge_method': 'S256',
    };
    final query = params.entries
        .map((e) => '${Uri.encodeComponent(e.key)}=${Uri.encodeComponent(e.value)}')
        .join('&');
    return '${SsoConfig.oidcAuthorizeUrl}?$query';
  }

  /// Exchanges authorization code for tokens.
  Future<OidcTokens> exchangeCode(String code) async {
    if (_codeVerifier == null) {
      throw Exception('PKCE verifier not set — call buildAuthorizeUrl first');
    }

    final resp = await _dio.post(
      SsoConfig.oidcTokenUrl,
      options: Options(
        contentType: Headers.formUrlEncodedContentType,
      ),
      data: {
        'grant_type': 'authorization_code',
        'client_id': SsoConfig.oidcClientId,
        'code': code,
        'redirect_uri': SsoConfig.oidcRedirectUri,
        'code_verifier': _codeVerifier,
      },
    );

    final data = resp.data as Map<String, dynamic>;
    final accessToken = data['access_token'] as String;
    final idToken = data['id_token'] as String?;
    final refreshToken = data['refresh_token'] as String?;

    // Get user info from Authentik
    final userResp = await _dio.get(
      SsoConfig.oidcUserInfoUrl,
      options: Options(headers: {'Authorization': 'Bearer $accessToken'}),
    );
    final userInfo = userResp.data as Map<String, dynamic>;

    _codeVerifier = null;

    return OidcTokens(
      accessToken: accessToken,
      idToken: idToken,
      refreshToken: refreshToken,
      email: (userInfo['email'] ?? '') as String,
      name: (userInfo['name'] ?? userInfo['preferred_username'] ?? '') as String,
    );
  }
}

final oidcAuthServiceProvider = Provider.autoDispose<OidcAuthService>(
  (ref) => OidcAuthService(),
);
