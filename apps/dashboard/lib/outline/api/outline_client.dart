import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/auth/auth_interceptor.dart';
import '../../app/auth/token_manager.dart';
import '../../shared/services/http_client.dart';
import 'endpoints.dart';

class OutlineClient {
  OutlineClient(this._dio);

  final Dio _dio;

  // Documents -- Outline uses POST for all API calls
  Future<Map<String, dynamic>> listDocuments({
    int offset = 0,
    int limit = 25,
    String? collectionId,
    String? sort = 'updatedAt',
    String? direction = 'DESC',
  }) async {
    final body = <String, dynamic>{
      'offset': offset,
      'limit': limit,
      'sort': sort,
      'direction': direction,
    };
    if (collectionId != null) body['collectionId'] = collectionId;

    final resp = await _dio.post(OutlineEndpoints.documentsList, data: body);
    return resp.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getDocument(String id) async {
    final resp = await _dio.post(
      OutlineEndpoints.documentsInfo,
      data: {'id': id},
    );
    return resp.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> createDocument({
    required String title,
    required String collectionId,
    String? text,
    bool publish = true,
  }) async {
    final resp = await _dio.post(
      OutlineEndpoints.documentsCreate,
      data: {
        'title': title,
        'collectionId': collectionId,
        'text': text ?? '',
        'publish': publish,
      },
    );
    return resp.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> updateDocument({
    required String id,
    String? title,
    String? text,
  }) async {
    final body = <String, dynamic>{'id': id};
    if (title != null) body['title'] = title;
    if (text != null) body['text'] = text;

    final resp = await _dio.post(OutlineEndpoints.documentsUpdate, data: body);
    return resp.data as Map<String, dynamic>;
  }

  Future<void> deleteDocument(String id) async {
    await _dio.post(OutlineEndpoints.documentsDelete, data: {'id': id});
  }

  Future<Map<String, dynamic>> searchDocuments(String query, {
    int offset = 0,
    int limit = 25,
  }) async {
    final resp = await _dio.post(
      OutlineEndpoints.documentsSearch,
      data: {
        'query': query,
        'offset': offset,
        'limit': limit,
      },
    );
    return resp.data as Map<String, dynamic>;
  }

  // Collections
  Future<Map<String, dynamic>> listCollections({
    int offset = 0,
    int limit = 25,
  }) async {
    final resp = await _dio.post(
      OutlineEndpoints.collectionsList,
      data: {'offset': offset, 'limit': limit},
    );
    return resp.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getCollection(String id) async {
    final resp = await _dio.post(
      OutlineEndpoints.collectionsInfo,
      data: {'id': id},
    );
    return resp.data as Map<String, dynamic>;
  }
}

final outlineClientProvider = Provider.autoDispose<OutlineClient>((ref) {
  final urls = ref.watch(backendUrlsProvider);
  final authState = ref.watch(tokenManagerProvider);

  final dio = createDio(
    baseUrl: urls.outline,
    interceptors: [
      AuthInterceptor(() => authState),
    ],
  );

  return OutlineClient(dio);
});
