import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/pbx_client.dart';

/// PBX extensions list.
final pbxExtensionsProvider =
    FutureProvider.autoDispose<List<Map<String, dynamic>>>((ref) async {
  final client = ref.watch(pbxClientProvider);
  return client.listExtensions();
});

/// PBX ring groups.
final pbxRingGroupsProvider =
    FutureProvider.autoDispose<List<Map<String, dynamic>>>((ref) async {
  final client = ref.watch(pbxClientProvider);
  return client.listRingGroups();
});

/// Day/night modes.
final pbxDayNightProvider =
    FutureProvider.autoDispose<List<Map<String, dynamic>>>((ref) async {
  final client = ref.watch(pbxClientProvider);
  return client.listDayNightModes();
});

/// Outbound routes.
final pbxOutboundRoutesProvider =
    FutureProvider.autoDispose<List<Map<String, dynamic>>>((ref) async {
  final client = ref.watch(pbxClientProvider);
  return client.listOutboundRoutes();
});

/// Inbound routes.
final pbxInboundRoutesProvider =
    FutureProvider.autoDispose<List<Map<String, dynamic>>>((ref) async {
  final client = ref.watch(pbxClientProvider);
  return client.listInboundRoutes();
});

/// Feature codes.
final pbxFeatureCodesProvider =
    FutureProvider.autoDispose<List<Map<String, dynamic>>>((ref) async {
  final client = ref.watch(pbxClientProvider);
  return client.listFeatureCodes();
});

/// System status.
final pbxStatusProvider =
    FutureProvider.autoDispose<Map<String, dynamic>>((ref) async {
  final client = ref.watch(pbxClientProvider);
  return client.getStatus();
});
