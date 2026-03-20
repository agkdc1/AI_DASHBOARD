import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// API client for PBX management endpoints on faxapi.
class PbxClient {
  PbxClient(this._dio);
  final Dio _dio;

  // -- Extensions --

  Future<List<Map<String, dynamic>>> listExtensions() async {
    final resp = await _dio.get('/extensions');
    final data = resp.data as Map<String, dynamic>;
    return (data['extensions'] as List).cast<Map<String, dynamic>>();
  }

  Future<Map<String, dynamic>> getExtension(String ext) async {
    final resp = await _dio.get('/extensions/$ext');
    return resp.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> createExtension({
    required String extension,
    required String name,
    String? password,
  }) async {
    final data = <String, dynamic>{
      'extension': extension,
      'name': name,
    };
    if (password != null) data['password'] = password;
    final resp = await _dio.post('/extensions', data: data);
    return resp.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> updateExtension(
    String ext, {
    String? name,
    String? password,
  }) async {
    final data = <String, dynamic>{};
    if (name != null) data['name'] = name;
    if (password != null) data['password'] = password;
    final resp = await _dio.put('/extensions/$ext', data: data);
    return resp.data as Map<String, dynamic>;
  }

  Future<void> deleteExtension(String ext) async {
    await _dio.delete('/extensions/$ext');
  }

  // -- Ring Groups --

  Future<List<Map<String, dynamic>>> listRingGroups() async {
    final resp = await _dio.get('/pbx/ring-groups');
    final data = resp.data as Map<String, dynamic>;
    return (data['ring_groups'] as List).cast<Map<String, dynamic>>();
  }

  Future<void> updateRingGroupMembers(int groupId, List<String> members) async {
    await _dio.put('/pbx/ring-groups/$groupId/members', data: {
      'members': members,
    });
  }

  // -- Day/Night Modes --

  Future<List<Map<String, dynamic>>> listDayNightModes() async {
    final resp = await _dio.get('/pbx/day-night');
    final data = resp.data as Map<String, dynamic>;
    return (data['modes'] as List).cast<Map<String, dynamic>>();
  }

  Future<Map<String, dynamic>> toggleDayNight(int modeId) async {
    final resp = await _dio.post('/pbx/day-night/$modeId/toggle');
    return resp.data as Map<String, dynamic>;
  }

  // -- Routes --

  Future<List<Map<String, dynamic>>> listOutboundRoutes() async {
    final resp = await _dio.get('/pbx/routes/outbound');
    final data = resp.data as Map<String, dynamic>;
    return (data['routes'] as List).cast<Map<String, dynamic>>();
  }

  Future<List<Map<String, dynamic>>> listInboundRoutes() async {
    final resp = await _dio.get('/pbx/routes/inbound');
    final data = resp.data as Map<String, dynamic>;
    return (data['routes'] as List).cast<Map<String, dynamic>>();
  }

  // -- Feature Codes --

  Future<List<Map<String, dynamic>>> listFeatureCodes() async {
    final resp = await _dio.get('/pbx/feature-codes');
    final data = resp.data as Map<String, dynamic>;
    return (data['feature_codes'] as List).cast<Map<String, dynamic>>();
  }

  // -- System --

  Future<Map<String, dynamic>> getStatus() async {
    final resp = await _dio.get('/pbx/status');
    return resp.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> reload() async {
    final resp = await _dio.post('/pbx/reload');
    return resp.data as Map<String, dynamic>;
  }
}

/// faxapi base URL.
const _faxapiUrl = String.fromEnvironment(
  'FAXAPI_URL',
  defaultValue: 'http://10.0.0.254:8010',
);

/// faxapi API key.
const _faxapiKey = String.fromEnvironment(
  'FAX_API_KEY',
  defaultValue: '',
);

final pbxClientProvider = Provider.autoDispose<PbxClient>((ref) {
  final dio = Dio(BaseOptions(
    baseUrl: _faxapiUrl,
    connectTimeout: const Duration(seconds: 15),
    receiveTimeout: const Duration(seconds: 30),
    headers: {
      'Accept': 'application/json',
      'Content-Type': 'application/json',
      if (_faxapiKey.isNotEmpty) 'X-API-Key': _faxapiKey,
    },
  ));
  return PbxClient(dio);
});
