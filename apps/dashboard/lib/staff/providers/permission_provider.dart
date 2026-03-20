import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/staff_client.dart';
import '../models/staff.dart';

/// Current user's IAM profile (role + permissions).
/// Cached until invalidated on sign-out.
final myPermissionsProvider =
    FutureProvider.autoDispose<IamProfile>((ref) async {
  final client = ref.watch(staffClientProvider);
  try {
    final data = await client.getMe();
    return IamProfile.fromJson(data);
  } catch (_) {
    // If IAM service unavailable, default to no restrictions
    return const IamProfile(
      registered: false,
      role: 'guest',
      denied: [],
      allPermissions: [],
    );
  }
});

/// Role-guaranteed permissions that cannot be denied.
const roleGuaranteed = <String, List<String>>{
  'admin': ['staff.manage', 'phone.admin'],
  'phone_admin': ['phone.admin'],
};
