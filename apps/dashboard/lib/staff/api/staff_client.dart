import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/auth/auth_state.dart';
import '../../app/auth/sso_config.dart';
import '../../app/auth/token_manager.dart';

/// API client for IAM endpoints on the AI assistant backend.
class StaffClient {
  StaffClient(this._dio);
  final Dio _dio;

  // -- My profile --

  Future<Map<String, dynamic>> getMe() async {
    final resp = await _dio.get('/iam/me');
    return resp.data as Map<String, dynamic>;
  }

  // -- Permissions --

  Future<Map<String, dynamic>> listPermissions() async {
    final resp = await _dio.get('/iam/permissions');
    return resp.data as Map<String, dynamic>;
  }

  // -- Staff CRUD --

  Future<List<Map<String, dynamic>>> listStaff() async {
    final resp = await _dio.get('/iam/staff');
    final data = resp.data as Map<String, dynamic>;
    return (data['staff'] as List).cast<Map<String, dynamic>>();
  }

  Future<Map<String, dynamic>> getStaff(String email) async {
    final resp = await _dio.get('/iam/staff/$email');
    return resp.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> createStaff({
    required String email,
    required String displayName,
    String role = 'staff',
    String? photoUrl,
  }) async {
    final resp = await _dio.post('/iam/staff', data: {
      'email': email,
      'display_name': displayName,
      'role': role,
      if (photoUrl != null) 'photo_url': photoUrl,
    });
    return resp.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> updateStaff(
    String email, {
    String? displayName,
    String? role,
    String? photoUrl,
  }) async {
    final data = <String, dynamic>{};
    if (displayName != null) data['display_name'] = displayName;
    if (role != null) data['role'] = role;
    if (photoUrl != null) data['photo_url'] = photoUrl;
    final resp = await _dio.put('/iam/staff/$email', data: data);
    return resp.data as Map<String, dynamic>;
  }

  Future<void> deleteStaff(String email) async {
    await _dio.delete('/iam/staff/$email');
  }

  Future<Map<String, dynamic>> setDenyRules(
    String email,
    List<String> permissions,
  ) async {
    final resp = await _dio.put('/iam/staff/$email/deny-rules', data: {
      'permissions': permissions,
    });
    return resp.data as Map<String, dynamic>;
  }
}

final staffClientProvider = Provider.autoDispose<StaffClient>((ref) {
  final authState = ref.watch(tokenManagerProvider);
  String? userEmail;
  if (authState is Authenticated) {
    userEmail = authState.email;
  }

  final dio = Dio(BaseOptions(
    baseUrl: SsoConfig.aiAssistantBaseUrl,
    connectTimeout: const Duration(seconds: 15),
    receiveTimeout: const Duration(seconds: 30),
    headers: {
      'Accept': 'application/json',
      'Content-Type': 'application/json',
      if (userEmail != null) 'X-User-Email': userEmail,
    },
  ));
  return StaffClient(dio);
});
