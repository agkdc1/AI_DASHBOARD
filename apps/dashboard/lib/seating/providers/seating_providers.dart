import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/seating_client.dart';
import '../models/floor_map.dart';
import '../models/office.dart';
import '../models/seat_assignment.dart';

/// All offices.
final officesProvider = FutureProvider.autoDispose<List<Office>>((ref) async {
  final client = ref.watch(seatingClientProvider);
  return client.listOffices();
});

/// Floors for a given office.
final floorsProvider =
    FutureProvider.autoDispose.family<List<Floor>, int>((ref, officeId) async {
  final client = ref.watch(seatingClientProvider);
  return client.listFloors(officeId);
});

/// Rooms for a given floor.
final roomsProvider =
    FutureProvider.autoDispose.family<List<Room>, int>((ref, floorId) async {
  final client = ref.watch(seatingClientProvider);
  return client.listRooms(floorId);
});

/// Floor map with desk statuses.
final floorMapProvider =
    FutureProvider.autoDispose.family<FloorMap, int>((ref, floorId) async {
  final client = ref.watch(seatingClientProvider);
  return client.getFloorMap(floorId);
});

/// Current user's active seat assignment.
final myAssignmentProvider =
    FutureProvider.autoDispose<SeatAssignment?>((ref) async {
  final client = ref.watch(seatingClientProvider);
  return client.getMyAssignment();
});

/// Assignment history for current user.
final assignmentHistoryProvider =
    FutureProvider.autoDispose<List<SeatAssignment>>((ref) async {
  final client = ref.watch(seatingClientProvider);
  return client.getHistory();
});
