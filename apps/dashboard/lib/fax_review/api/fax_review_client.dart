import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

class FaxReviewClient {
  FaxReviewClient(this._dio);
  final Dio _dio;

  /// List pending fax PDF+Doc pairs from the review folder.
  Future<List<Map<String, dynamic>>> listPending() async {
    final resp = await _dio.get('/fax-review/pending');
    return (resp.data as List).cast<Map<String, dynamic>>();
  }

  /// Approve a fax pair — move files to 'reviewed' folder.
  Future<Map<String, dynamic>> approve({
    String? docId,
    String? pdfId,
  }) async {
    final resp = await _dio.post('/fax-review/approve', data: {
      'doc_id': docId,
      'pdf_id': pdfId,
    });
    return resp.data as Map<String, dynamic>;
  }
}

const _aiAssistantUrl = String.fromEnvironment(
  'AI_ASSISTANT_URL',
  defaultValue: 'https://ai.your-domain.com',
);

final faxReviewClientProvider =
    Provider.autoDispose<FaxReviewClient>((ref) {
  final dio = Dio(BaseOptions(
    baseUrl: _aiAssistantUrl,
    connectTimeout: const Duration(seconds: 15),
    receiveTimeout: const Duration(seconds: 30),
    headers: {
      'Accept': 'application/json',
      'Content-Type': 'application/json',
    },
  ));
  return FaxReviewClient(dio);
});
