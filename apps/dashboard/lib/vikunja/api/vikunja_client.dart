import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/auth/auth_interceptor.dart';
import '../../app/auth/token_manager.dart';
import '../../shared/services/http_client.dart';
import 'endpoints.dart';

class VikunjaClient {
  VikunjaClient(this._dio);

  final Dio _dio;

  // Projects
  Future<List<dynamic>> getProjects({int page = 1, int perPage = 50}) async {
    final resp = await _dio.get(
      VikunjaEndpoints.projects,
      queryParameters: {'page': page, 'per_page': perPage},
    );
    return resp.data as List<dynamic>;
  }

  Future<Map<String, dynamic>> getProject(int id) async {
    final resp = await _dio.get('${VikunjaEndpoints.projects}/$id');
    return resp.data as Map<String, dynamic>;
  }

  // Tasks
  Future<List<dynamic>> getProjectTasks(int projectId, {
    int page = 1,
    int perPage = 50,
    String? sort,
    String? filter,
  }) async {
    final params = <String, dynamic>{
      'page': page,
      'per_page': perPage,
    };
    if (sort != null) params['sort_by'] = sort;
    if (filter != null) params['filter'] = filter;

    final resp = await _dio.get(
      VikunjaEndpoints.projectTasks(projectId),
      queryParameters: params,
    );
    return resp.data as List<dynamic>;
  }

  Future<Map<String, dynamic>> getTask(int id) async {
    final resp = await _dio.get(VikunjaEndpoints.task(id));
    return resp.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> createTask(int projectId, Map<String, dynamic> data) async {
    final resp = await _dio.put(
      VikunjaEndpoints.projectTasks(projectId),
      data: data,
    );
    return resp.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> updateTask(int taskId, Map<String, dynamic> data) async {
    final resp = await _dio.post(
      VikunjaEndpoints.task(taskId),
      data: data,
    );
    return resp.data as Map<String, dynamic>;
  }

  Future<void> deleteTask(int taskId) async {
    await _dio.delete(VikunjaEndpoints.task(taskId));
  }

  // Buckets (Kanban)
  Future<List<dynamic>> getBuckets(int projectId) async {
    final resp = await _dio.get(VikunjaEndpoints.projectBuckets(projectId));
    return resp.data as List<dynamic>;
  }

  // Labels
  Future<List<dynamic>> getLabels() async {
    final resp = await _dio.get(VikunjaEndpoints.labels);
    return resp.data as List<dynamic>;
  }
}

final vikunjaClientProvider = Provider.autoDispose<VikunjaClient>((ref) {
  final urls = ref.watch(backendUrlsProvider);
  final authState = ref.watch(tokenManagerProvider);

  final dio = createDio(
    baseUrl: urls.vikunja,
    interceptors: [
      AuthInterceptor(() => authState),
    ],
  );

  return VikunjaClient(dio);
});
