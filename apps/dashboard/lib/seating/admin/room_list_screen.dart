import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shinbee_dashboard/shared/l10n/generated/app_localizations.dart';

import '../api/seating_client.dart';
import '../providers/seating_providers.dart';

/// Room CRUD list for a given floor.
class RoomListScreen extends ConsumerWidget {
  final int floorId;

  const RoomListScreen({super.key, required this.floorId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = S.of(context);
    final roomsAsync = ref.watch(roomsProvider(floorId));

    return Scaffold(
      appBar: AppBar(title: Text(l10n.seatRooms)),
      body: roomsAsync.when(
        data: (rooms) {
          if (rooms.isEmpty) {
            return Center(child: Text(l10n.seatNoRooms));
          }
          return ListView.builder(
            itemCount: rooms.length,
            itemBuilder: (context, index) {
              final room = rooms[index];
              return ListTile(
                leading: const Icon(Icons.meeting_room),
                title: Text(room.displayName),
                subtitle: Text('Room ${room.roomNumber}'),
              );
            },
          );
        },
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () => _addRoom(context, ref),
        child: const Icon(Icons.add),
      ),
    );
  }

  Future<void> _addRoom(BuildContext context, WidgetRef ref) async {
    final l10n = S.of(context);
    final numberCtrl = TextEditingController();
    final nameCtrl = TextEditingController();

    final result = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(l10n.seatAddRoom),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: numberCtrl,
              decoration: InputDecoration(labelText: l10n.seatRoomNumber),
              keyboardType: TextInputType.number,
            ),
            const SizedBox(height: 8),
            TextField(
              controller: nameCtrl,
              decoration: InputDecoration(labelText: l10n.seatRoomName),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: Text(l10n.cancel),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: Text(l10n.save),
          ),
        ],
      ),
    );

    if (result == true && numberCtrl.text.isNotEmpty) {
      final client = ref.read(seatingClientProvider);
      await client.createRoom(
        floorId: floorId,
        roomNumber: int.parse(numberCtrl.text),
        name: nameCtrl.text.isNotEmpty ? nameCtrl.text : null,
      );
      ref.invalidate(roomsProvider(floorId));
    }
  }
}
