import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/phone_client.dart';
import '../models/phone_user.dart';
import '../models/phone_device.dart';

final phoneUsersProvider =
    FutureProvider.autoDispose<List<PhoneUser>>((ref) async {
  final client = ref.watch(phoneClientProvider);
  final data = await client.listUsers();
  return data.map((e) => PhoneUser.fromJson(e)).toList();
});

final phoneDevicesProvider =
    FutureProvider.autoDispose<List<PhoneDevice>>((ref) async {
  final client = ref.watch(phoneClientProvider);
  final data = await client.listDevices();
  return data.map((e) => PhoneDevice.fromJson(e)).toList();
});
