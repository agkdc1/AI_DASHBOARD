import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart' show kIsWeb;

import 'auth_state.dart';
import 'cookie_helper.dart';

/// Interceptor for Authentik forward-auth cookie-based authentication.
///
/// For InvenTree/Vikunja/Outline: the browser sends the Authentik session
/// cookie automatically (withCredentials=true). No Authorization header needed.
/// For AI assistant: passes X-User-Email header.
/// For InvenTree writes: reads csrftoken cookie and sets X-CSRFToken header.
class AuthInterceptor extends Interceptor {
  AuthInterceptor(this._getAuthState);

  final AuthState Function() _getAuthState;

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    // Enable cookie sending for cross-origin requests (web)
    if (kIsWeb) {
      options.extra['withCredentials'] = true;
    }

    final state = _getAuthState();
    if (state is Authenticated) {
      final host = options.uri.host;

      if (host.contains('ai')) {
        // AI assistant uses email header for user identification
        options.headers['X-User-Email'] = state.email;
      }

      // InvenTree CSRF token for mutating requests
      if ((host.contains('portal') || host.contains('api')) &&
          options.method != 'GET' &&
          options.method != 'HEAD') {
        final csrf = readCsrfToken();
        if (csrf != null) {
          options.headers['X-CSRFToken'] = csrf;
        }
      }
    }
    handler.next(options);
  }

  @override
  void onError(DioException err, ErrorInterceptorHandler handler) {
    if (err.response?.statusCode == 401 || err.response?.statusCode == 302) {
      // Session expired — forward auth will redirect to Authentik login
    }
    handler.next(err);
  }
}
