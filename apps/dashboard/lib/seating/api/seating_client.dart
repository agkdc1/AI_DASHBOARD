import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/auth/auth_state.dart';
import '../../app/auth/sso_config.dart';
import '../../app/auth/token_manager.dart';
import '../models/floor_map.dart';
import '../models/office.dart';
import '../models/seat_assignment.dart';

/// API client for seating / hot-desking endpoints on the AI assistant backend.
class SeatingClient {
  SeatingClient(this._dio);
  final Dio _dio;

  // -- Offices --

  Future<List<Office>> listOffices() async {
    final resp = await _dio.get('/seating/offices');
    final data = resp.data as Map<String, dynamic>;
    return (data['offices'] as List)
        .map((e) => Office.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<Office> createOffice({required String name, String? address}) async {
    final resp = await _dio.post('/seating/offices', data: {
      'name': name,
      if (address != null) 'address': address,
    });
    return Office.fromJson(resp.data as Map<String, dynamic>);
  }

  // -- Floors --

  Future<List<Floor>> listFloors(int officeId) async {
    final resp =
        await _dio.get('/seating/floors', queryParameters: {'office_id': officeId});
    final data = resp.data as Map<String, dynamic>;
    return (data['floors'] as List)
        .map((e) => Floor.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<Floor> createFloor({
    required int officeId,
    required int floorNumber,
    String? name,
  }) async {
    final resp = await _dio.post('/seating/floors', data: {
      'office_id': officeId,
      'floor_number': floorNumber,
      if (name != null) 'name': name,
    });
    return Floor.fromJson(resp.data as Map<String, dynamic>);
  }

  Future<void> uploadFloorplan(int floorId, Uint8List bytes, String filename) async {
    final formData = FormData.fromMap({
      'file': MultipartFile.fromBytes(bytes, filename: filename),
    });
    await _dio.post('/seating/floors/$floorId/floorplan', data: formData);
  }

  String getFloorplanUrl(int floorId) =>
      '${_dio.options.baseUrl}/seating/floors/$floorId/floorplan';

  // -- Rooms --

  Future<List<Room>> listRooms(int floorId) async {
    final resp =
        await _dio.get('/seating/rooms', queryParameters: {'floor_id': floorId});
    final data = resp.data as Map<String, dynamic>;
    return (data['rooms'] as List)
        .map((e) => Room.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<Room> createRoom({
    required int floorId,
    required int roomNumber,
    String? name,
  }) async {
    final resp = await _dio.post('/seating/rooms', data: {
      'floor_id': floorId,
      'room_number': roomNumber,
      if (name != null) 'name': name,
    });
    return Room.fromJson(resp.data as Map<String, dynamic>);
  }

  // -- Desks --

  Future<Desk> createDesk({
    required int roomId,
    required int deskNumber,
    String? phoneMac,
    String phoneModel = 'GXP1760W',
    String deskType = 'open',
    String? designatedEmail,
    double? posX,
    double? posY,
  }) async {
    final resp = await _dio.post('/seating/desks', data: {
      'room_id': roomId,
      'desk_number': deskNumber,
      if (phoneMac != null) 'phone_mac': phoneMac,
      'phone_model': phoneModel,
      'desk_type': deskType,
      if (designatedEmail != null) 'designated_email': designatedEmail,
      if (posX != null) 'pos_x': posX,
      if (posY != null) 'pos_y': posY,
    });
    return Desk.fromJson(resp.data as Map<String, dynamic>);
  }

  Future<Desk> updateDesk(int deskId, Map<String, dynamic> updates) async {
    final resp = await _dio.put('/seating/desks/$deskId', data: updates);
    return Desk.fromJson(resp.data as Map<String, dynamic>);
  }

  Future<void> deleteDesk(int deskId) async {
    await _dio.delete('/seating/desks/$deskId');
  }

  // -- Floor Map --

  Future<FloorMap> getFloorMap(int floorId) async {
    final resp = await _dio.get('/seating/floors/$floorId/map');
    return FloorMap.fromJson(resp.data as Map<String, dynamic>);
  }

  // -- Check-in / Check-out --

  Future<SeatAssignment?> getMyAssignment() async {
    final resp = await _dio.get('/seating/my-seat');
    final data = resp.data as Map<String, dynamic>;
    if (data['assignment'] == null) return null;
    return SeatAssignment.fromJson(data['assignment'] as Map<String, dynamic>);
  }

  Future<SeatAssignment> checkIn(int deskId) async {
    final resp = await _dio.post('/seating/check-in', data: {'desk_id': deskId});
    return SeatAssignment.fromJson(resp.data as Map<String, dynamic>);
  }

  Future<SeatAssignment> checkOut({int? deskId}) async {
    final resp = await _dio.post('/seating/check-out', data: {
      if (deskId != null) 'desk_id': deskId,
    });
    return SeatAssignment.fromJson(resp.data as Map<String, dynamic>);
  }

  // -- History --

  Future<List<SeatAssignment>> getHistory({int limit = 20}) async {
    final resp = await _dio
        .get('/seating/history', queryParameters: {'limit': limit});
    final data = resp.data as Map<String, dynamic>;
    return (data['history'] as List)
        .map((e) => SeatAssignment.fromJson(e as Map<String, dynamic>))
        .toList();
  }
}

final seatingClientProvider = Provider.autoDispose<SeatingClient>((ref) {
  final authState = ref.watch(tokenManagerProvider);
  String? userEmail;
  String? userName;
  if (authState is Authenticated) {
    userEmail = authState.email;
    userName = authState.displayName;
  }

  final dio = Dio(BaseOptions(
    baseUrl: SsoConfig.aiAssistantBaseUrl,
    connectTimeout: const Duration(seconds: 15),
    receiveTimeout: const Duration(seconds: 30),
    headers: {
      'Accept': 'application/json',
      'Content-Type': 'application/json',
      if (userEmail != null && userEmail.isNotEmpty)
        'X-User-Email': userEmail,
      if (userName != null)
        'X-User-Name': base64Encode(utf8.encode(userName)),
    },
    extra: kIsWeb ? {'withCredentials': true} : null,
  ));
  return SeatingClient(dio);
});
