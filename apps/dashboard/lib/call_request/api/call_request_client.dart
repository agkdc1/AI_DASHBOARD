import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// API client for call-request endpoints on the AI assistant backend.
class CallRequestClient {
  CallRequestClient(this._dio);
  final Dio _dio;

  /// Originate a recorded call between two extensions.
  /// Returns `{"call_id": "...", "status": "ringing"}`.
  Future<Map<String, dynamic>> initiateCall({
    required String callerExt,
    required String targetExt,
  }) async {
    final resp = await _dio.post('/call-request/initiate', data: {
      'caller_ext': callerExt,
      'target_ext': targetExt,
    });
    return resp.data as Map<String, dynamic>;
  }

  /// Check call status (ringing, in_progress, completed, error).
  Future<Map<String, dynamic>> getStatus(String callId) async {
    final resp = await _dio.get('/call-request/$callId/status');
    return resp.data as Map<String, dynamic>;
  }

  /// Transcribe, mask PII, and analyze the call recording with Gemini.
  /// Returns analysis with title, description, due_date, priority, decisions.
  Future<Map<String, dynamic>> analyzeRecording(
    String callId, {
    String callerEmail = '',
    String targetEmail = '',
  }) async {
    final resp = await _dio.post('/call-request/$callId/analyze', data: {
      'caller_email': callerEmail,
      'target_email': targetEmail,
    });
    return resp.data as Map<String, dynamic>;
  }

  /// Create a Vikunja task from the analyzed call.
  /// Returns `{"task_created": true, "task_id": ...}`.
  Future<Map<String, dynamic>> confirmCall(
    String callId, {
    int projectId = 1,
  }) async {
    final resp = await _dio.post('/call-request/$callId/confirm', data: {
      'project_id': projectId,
    });
    return resp.data as Map<String, dynamic>;
  }
}

const _aiAssistantUrl = String.fromEnvironment(
  'AI_ASSISTANT_URL',
  defaultValue: 'https://ai.your-domain.com',
);

final callRequestClientProvider =
    Provider.autoDispose<CallRequestClient>((ref) {
  final dio = Dio(BaseOptions(
    baseUrl: _aiAssistantUrl,
    connectTimeout: const Duration(seconds: 15),
    receiveTimeout: const Duration(seconds: 60),
    headers: {
      'Accept': 'application/json',
      'Content-Type': 'application/json',
    },
  ));
  return CallRequestClient(dio);
});
