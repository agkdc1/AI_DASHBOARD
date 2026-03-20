import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/staff_client.dart';
import '../models/staff.dart';

/// All registered staff members.
final staffListProvider =
    FutureProvider.autoDispose<List<StaffMember>>((ref) async {
  final client = ref.watch(staffClientProvider);
  final data = await client.listStaff();
  return data.map((e) => StaffMember.fromJson(e)).toList();
});

/// Single staff member detail.
final staffDetailProvider = FutureProvider.autoDispose
    .family<StaffMember, String>((ref, email) async {
  final client = ref.watch(staffClientProvider);
  final data = await client.getStaff(email);
  return StaffMember.fromJson(data);
});

/// All permission definitions from the backend.
final permissionsDefProvider =
    FutureProvider.autoDispose<List<PermissionDef>>((ref) async {
  final client = ref.watch(staffClientProvider);
  final data = await client.listPermissions();
  final perms = data['permissions'] as List;
  return perms
      .map((e) => PermissionDef.fromJson(e as Map<String, dynamic>))
      .toList();
});
