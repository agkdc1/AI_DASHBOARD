import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// API client for phone admin endpoints on the AI assistant backend.
class PhoneClient {
  PhoneClient(this._dio);
  final Dio _dio;

  // -- LDAP Users --

  Future<List<Map<String, dynamic>>> listUsers() async {
    final resp = await _dio.get('/phone/users');
    return (resp.data as List).cast<Map<String, dynamic>>();
  }

  Future<Map<String, dynamic>> getUser(String uid) async {
    final resp = await _dio.get('/phone/users/$uid');
    return resp.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> createUser({
    required String uid,
    required String cn,
    String password = '1234',
  }) async {
    final resp = await _dio.post('/phone/users', data: {
      'uid': uid,
      'cn': cn,
      'password': password,
    });
    return resp.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> updateUser(
    String uid, {
    String? cn,
    String? password,
  }) async {
    final data = <String, dynamic>{};
    if (cn != null) data['cn'] = cn;
    if (password != null) data['password'] = password;
    final resp = await _dio.put('/phone/users/$uid', data: data);
    return resp.data as Map<String, dynamic>;
  }

  Future<void> deleteUser(String uid) async {
    await _dio.delete('/phone/users/$uid');
  }

  // -- Devices --

  Future<List<Map<String, dynamic>>> listDevices() async {
    final resp = await _dio.get('/phone/devices');
    return (resp.data as List).cast<Map<String, dynamic>>();
  }
}

/// The AI assistant base URL for phone admin API.
const _aiAssistantUrl = String.fromEnvironment(
  'AI_ASSISTANT_URL',
  defaultValue: 'https://ai.your-domain.com',
);

final phoneClientProvider = Provider.autoDispose<PhoneClient>((ref) {
  final dio = Dio(BaseOptions(
    baseUrl: _aiAssistantUrl,
    connectTimeout: const Duration(seconds: 15),
    receiveTimeout: const Duration(seconds: 30),
    headers: {
      'Accept': 'application/json',
      'Content-Type': 'application/json',
    },
  ));
  return PhoneClient(dio);
});
