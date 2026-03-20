import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/auth/auth_interceptor.dart';
import '../../app/auth/token_manager.dart';
import '../../shared/services/http_client.dart';
import 'endpoints.dart';

class InvenTreeClient {
  InvenTreeClient(this._dio);

  final Dio _dio;

  // Parts
  Future<Map<String, dynamic>> getParts({
    int limit = 25,
    int offset = 0,
    String? search,
    int? categoryId,
    bool? active,
  }) async {
    final params = <String, dynamic>{
      'limit': limit,
      'offset': offset,
    };
    if (search != null) params['search'] = search;
    if (categoryId != null) params['category'] = categoryId;
    if (active != null) params['active'] = active;

    final resp = await _dio.get(
      InvenTreeEndpoints.parts,
      queryParameters: params,
    );
    return resp.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getPart(int id) async {
    final resp = await _dio.get('${InvenTreeEndpoints.parts}$id/');
    return resp.data as Map<String, dynamic>;
  }

  // Part Categories
  Future<Map<String, dynamic>> getPartCategories({
    int limit = 25,
    int offset = 0,
    int? parentId,
  }) async {
    final params = <String, dynamic>{
      'limit': limit,
      'offset': offset,
    };
    if (parentId != null) params['parent'] = parentId;

    final resp = await _dio.get(
      InvenTreeEndpoints.partCategories,
      queryParameters: params,
    );
    return resp.data as Map<String, dynamic>;
  }

  // Stock
  Future<Map<String, dynamic>> getStockItems({
    int limit = 25,
    int offset = 0,
    String? search,
    int? partId,
    int? locationId,
  }) async {
    final params = <String, dynamic>{
      'limit': limit,
      'offset': offset,
      'part_detail': true,
      'location_detail': true,
    };
    if (search != null) params['search'] = search;
    if (partId != null) params['part'] = partId;
    if (locationId != null) params['location'] = locationId;

    final resp = await _dio.get(
      InvenTreeEndpoints.stock,
      queryParameters: params,
    );
    return resp.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getStockItem(int id) async {
    final resp = await _dio.get(
      '${InvenTreeEndpoints.stock}$id/',
      queryParameters: {'part_detail': true, 'location_detail': true},
    );
    return resp.data as Map<String, dynamic>;
  }

  // Stock Locations
  Future<Map<String, dynamic>> getStockLocations({
    int limit = 25,
    int offset = 0,
    int? parentId,
  }) async {
    final params = <String, dynamic>{
      'limit': limit,
      'offset': offset,
    };
    if (parentId != null) params['parent'] = parentId;

    final resp = await _dio.get(
      InvenTreeEndpoints.stockLocations,
      queryParameters: params,
    );
    return resp.data as Map<String, dynamic>;
  }

  // Purchase Orders
  Future<Map<String, dynamic>> getPurchaseOrders({
    int limit = 25,
    int offset = 0,
    bool? outstanding,
  }) async {
    final params = <String, dynamic>{
      'limit': limit,
      'offset': offset,
      'supplier_detail': true,
    };
    if (outstanding != null) params['outstanding'] = outstanding;

    final resp = await _dio.get(
      InvenTreeEndpoints.purchaseOrders,
      queryParameters: params,
    );
    return resp.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getPurchaseOrder(int id) async {
    final resp = await _dio.get(
      '${InvenTreeEndpoints.purchaseOrders}$id/',
      queryParameters: {'supplier_detail': true},
    );
    return resp.data as Map<String, dynamic>;
  }

  // Sales Orders
  Future<Map<String, dynamic>> getSalesOrders({
    int limit = 25,
    int offset = 0,
    bool? outstanding,
  }) async {
    final params = <String, dynamic>{
      'limit': limit,
      'offset': offset,
      'customer_detail': true,
    };
    if (outstanding != null) params['outstanding'] = outstanding;

    final resp = await _dio.get(
      InvenTreeEndpoints.salesOrders,
      queryParameters: params,
    );
    return resp.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getSalesOrder(int id) async {
    final resp = await _dio.get(
      '${InvenTreeEndpoints.salesOrders}$id/',
      queryParameters: {'customer_detail': true},
    );
    return resp.data as Map<String, dynamic>;
  }

  // Sales Order Lines (for picking)
  Future<Map<String, dynamic>> getSalesOrderLines({
    int limit = 100,
    int offset = 0,
    int? orderId,
  }) async {
    final params = <String, dynamic>{
      'limit': limit,
      'offset': offset,
      'part_detail': true,
    };
    if (orderId != null) params['order'] = orderId;

    final resp = await _dio.get(
      InvenTreeEndpoints.salesOrderLines,
      queryParameters: params,
    );
    return resp.data as Map<String, dynamic>;
  }

  // Sales Order Allocations
  Future<Map<String, dynamic>> getSalesOrderAllocations({
    int limit = 100,
    int? orderId,
    int? lineId,
  }) async {
    final params = <String, dynamic>{'limit': limit};
    if (orderId != null) params['order'] = orderId;
    if (lineId != null) params['line'] = lineId;

    final resp = await _dio.get(
      InvenTreeEndpoints.salesOrderAllocations,
      queryParameters: params,
    );
    return resp.data as Map<String, dynamic>;
  }

  // Update Sales Order metadata (for company ID)
  Future<Map<String, dynamic>> updateSalesOrderMetadata(
    int orderId,
    Map<String, dynamic> metadata,
  ) async {
    // PATCH the SO with updated metadata
    final resp = await _dio.patch(
      '${InvenTreeEndpoints.salesOrders}$orderId/',
      data: {'metadata': metadata},
    );
    return resp.data as Map<String, dynamic>;
  }

  // Barcode scan
  Future<Map<String, dynamic>> scanBarcode(String barcode) async {
    final resp = await _dio.post(
      InvenTreeEndpoints.barcodeScan,
      data: {'barcode': barcode},
    );
    return resp.data as Map<String, dynamic>;
  }

  // Search
  Future<Map<String, dynamic>> search(String query, {int limit = 10}) async {
    final resp = await _dio.post(
      InvenTreeEndpoints.search,
      data: {
        'search': query,
        'limit': limit,
        'part': {},
        'stock': {},
        'purchaseorder': {},
        'salesorder': {},
      },
    );
    return resp.data as Map<String, dynamic>;
  }

  // Waybill (plugin)
  Future<Map<String, dynamic>> generateWaybill(
      Map<String, dynamic> data) async {
    final resp = await _dio.post(InvenTreeEndpoints.waybillGenerate, data: data);
    return resp.data as Map<String, dynamic>;
  }

  Future<List<int>> getWaybillPdf(String jobId) async {
    final resp = await _dio.get(
      '${InvenTreeEndpoints.waybillPdf}/$jobId',
      options: Options(responseType: ResponseType.bytes),
    );
    return resp.data as List<int>;
  }
}

final inventreeClientProvider = Provider.autoDispose<InvenTreeClient>((ref) {
  final urls = ref.watch(backendUrlsProvider);
  final authState = ref.watch(tokenManagerProvider);

  final dio = createDio(
    baseUrl: urls.inventree,
    interceptors: [
      AuthInterceptor(() => authState),
    ],
  );

  return InvenTreeClient(dio);
});
