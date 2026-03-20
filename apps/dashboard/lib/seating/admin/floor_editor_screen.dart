import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';
import 'package:shinbee_dashboard/shared/l10n/generated/app_localizations.dart';

import '../api/seating_client.dart';
import '../providers/seating_providers.dart';
import '../widgets/floor_plan_widget.dart';
import 'desk_config_dialog.dart';
import 'room_list_screen.dart';

/// Admin screen for editing a floor plan and placing desk pins.
class FloorEditorScreen extends ConsumerStatefulWidget {
  final int floorId;

  const FloorEditorScreen({super.key, required this.floorId});

  @override
  ConsumerState<FloorEditorScreen> createState() => _FloorEditorScreenState();
}

class _FloorEditorScreenState extends ConsumerState<FloorEditorScreen> {
  @override
  Widget build(BuildContext context) {
    final l10n = S.of(context);
    final mapAsync = ref.watch(floorMapProvider(widget.floorId));
    final roomsAsync = ref.watch(roomsProvider(widget.floorId));
    final client = ref.read(seatingClientProvider);

    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.seatFloorEditor),
        actions: [
          IconButton(
            icon: const Icon(Icons.meeting_room),
            tooltip: l10n.seatRooms,
            onPressed: () => Navigator.push(
              context,
              MaterialPageRoute(
                builder: (_) => RoomListScreen(floorId: widget.floorId),
              ),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.upload_file),
            tooltip: l10n.seatUploadFloorplan,
            onPressed: () => _uploadFloorplan(client),
          ),
        ],
      ),
      body: mapAsync.when(
        data: (floorMap) {
          final floorplanUrl = floorMap.floor.floorplanImage != null
              ? client.getFloorplanUrl(widget.floorId)
              : null;

          return FloorPlanWidget(
            floorplanUrl: floorplanUrl,
            desks: floorMap.desks,
            editMode: true,
            onTapEmpty: (x, y) {
              roomsAsync.whenData((rooms) {
                if (rooms.isEmpty) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(content: Text(l10n.seatAddRoomFirst)),
                  );
                  return;
                }
                _addDeskAtPosition(client, rooms, x, y);
              });
            },
            onTapDesk: (deskStatus) {
              _showDeskInfo(context, deskStatus);
            },
            onDeskMoved: (deskStatus, x, y) {
              _moveDeskTo(client, deskStatus, x, y);
            },
          );
        },
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
      ),
    );
  }

  Future<void> _uploadFloorplan(SeatingClient client) async {
    final picker = ImagePicker();
    final picked = await picker.pickImage(source: ImageSource.gallery);
    if (picked == null) return;

    final bytes = await picked.readAsBytes();
    await client.uploadFloorplan(widget.floorId, bytes, picked.name);
    ref.invalidate(floorMapProvider(widget.floorId));
  }

  Future<void> _addDeskAtPosition(
    SeatingClient client,
    List rooms,
    double x,
    double y,
  ) async {
    final result = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (ctx) => DeskConfigDialog(
        rooms: rooms.cast(),
        posX: x,
        posY: y,
      ),
    );

    if (result != null) {
      await client.createDesk(
        roomId: result['room_id'] as int,
        deskNumber: result['desk_number'] as int,
        deskType: result['desk_type'] as String,
        phoneMac: result['phone_mac'] as String?,
        designatedEmail: result['designated_email'] as String?,
        posX: result['pos_x'] as double?,
        posY: result['pos_y'] as double?,
      );
      ref.invalidate(floorMapProvider(widget.floorId));
    }
  }

  Future<void> _moveDeskTo(
    SeatingClient client,
    deskStatus,
    double x,
    double y,
  ) async {
    try {
      await client.updateDesk(deskStatus.desk.id, {
        'pos_x': x,
        'pos_y': y,
      });
      ref.invalidate(floorMapProvider(widget.floorId));
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to save position: $e')),
        );
      }
    }
  }

  void _showDeskInfo(BuildContext context, deskStatus) {
    final l10n = S.of(context);
    final desk = deskStatus.desk;
    showModalBottomSheet(
      context: context,
      builder: (ctx) => Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Ext ${desk.deskExtension}',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 8),
            Text('${l10n.seatDeskType}: ${desk.deskType}'),
            if (desk.phoneMac != null) Text('MAC: ${desk.phoneMac}'),
            if (desk.posX != null)
              Text('Position: (${(desk.posX! * 100).toStringAsFixed(1)}%, '
                  '${(desk.posY! * 100).toStringAsFixed(1)}%)'),
            if (deskStatus.isOccupied)
              Text(
                  '${l10n.seatOccupiedBy}: ${deskStatus.currentAssignment.employeeName}'),
            const SizedBox(height: 16),
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                TextButton(
                  onPressed: () async {
                    Navigator.pop(ctx);
                    final client = ref.read(seatingClientProvider);
                    await client.deleteDesk(desk.id);
                    ref.invalidate(floorMapProvider(widget.floorId));
                  },
                  child: Text(l10n.delete,
                      style: const TextStyle(color: Colors.red)),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
