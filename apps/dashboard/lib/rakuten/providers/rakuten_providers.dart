import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/auth/sso_config.dart';

final _dio = Dio(BaseOptions(baseUrl: SsoConfig.aiAssistantBaseUrl));

final rakutenStatusProvider = FutureProvider<Map<String, dynamic>>((ref) async {
  final resp = await _dio.get('/rakuten/status');
  return resp.data as Map<String, dynamic>;
});

final rakutenSubmitProvider = FutureProvider.family<Map<String, dynamic>,
    ({String serviceSecret, String licenseKey})>((ref, params) async {
  final resp = await _dio.post('/rakuten/keys', data: {
    'service_secret': params.serviceSecret,
    'license_key': params.licenseKey,
  });
  return resp.data as Map<String, dynamic>;
});
