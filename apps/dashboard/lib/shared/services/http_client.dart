import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter_riverpod/flutter_riverpod.dart';

class BackendUrls {
  const BackendUrls({
    this.inventree = 'https://portal.your-domain.com',
    this.vikunja = 'https://tasks.your-domain.com',
    this.outline = 'https://wiki.your-domain.com',
  });

  final String inventree;
  final String vikunja;
  final String outline;

  factory BackendUrls.fromEnvironment() {
    return const BackendUrls(
      inventree: String.fromEnvironment(
        'INVENTREE_URL',
        defaultValue: 'https://portal.your-domain.com',
      ),
      vikunja: String.fromEnvironment(
        'VIKUNJA_URL',
        defaultValue: 'https://tasks.your-domain.com',
      ),
      outline: String.fromEnvironment(
        'OUTLINE_URL',
        defaultValue: 'https://wiki.your-domain.com',
      ),
    );
  }
}

final backendUrlsProvider = Provider.autoDispose<BackendUrls>(
  (ref) => BackendUrls.fromEnvironment(),
);

Dio createDio({String? baseUrl, List<Interceptor>? interceptors}) {
  final dio = Dio(BaseOptions(
    baseUrl: baseUrl ?? '',
    connectTimeout: const Duration(seconds: 15),
    receiveTimeout: const Duration(seconds: 30),
    headers: {
      'Accept': 'application/json',
      'Content-Type': 'application/json',
    },
    // Send cookies cross-origin for Authentik forward auth
    extra: kIsWeb ? {'withCredentials': true} : null,
  ));

  if (interceptors != null) {
    dio.interceptors.addAll(interceptors);
  }

  return dio;
}
