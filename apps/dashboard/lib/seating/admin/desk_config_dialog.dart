import 'package:flutter/material.dart';
import 'package:shinbee_dashboard/shared/l10n/generated/app_localizations.dart';

import '../models/office.dart';

/// Dialog for configuring a new or existing desk on the floor plan.
class DeskConfigDialog extends StatefulWidget {
  final List<Room> rooms;
  final int? preselectedRoomId;
  final double? posX;
  final double? posY;

  const DeskConfigDialog({
    super.key,
    required this.rooms,
    this.preselectedRoomId,
    this.posX,
    this.posY,
  });

  @override
  State<DeskConfigDialog> createState() => _DeskConfigDialogState();
}

class _DeskConfigDialogState extends State<DeskConfigDialog> {
  late int? _selectedRoomId;
  final _deskNumberCtrl = TextEditingController();
  final _phoneMacCtrl = TextEditingController();
  String _deskType = 'open';
  final _designatedEmailCtrl = TextEditingController();
  String _computedExtension = '';

  @override
  void initState() {
    super.initState();
    _selectedRoomId = widget.preselectedRoomId ?? widget.rooms.firstOrNull?.id;
    _deskNumberCtrl.addListener(_updateExtension);
  }

  @override
  void dispose() {
    _deskNumberCtrl.dispose();
    _phoneMacCtrl.dispose();
    _designatedEmailCtrl.dispose();
    super.dispose();
  }

  void _updateExtension() {
    if (_selectedRoomId == null || _deskNumberCtrl.text.isEmpty) {
      setState(() => _computedExtension = '');
      return;
    }
    final room = widget.rooms.firstWhere((r) => r.id == _selectedRoomId);
    final deskNum = int.tryParse(_deskNumberCtrl.text);
    if (deskNum == null) {
      setState(() => _computedExtension = '');
      return;
    }
    // We don't have the floor number here easily, so just show room+desk
    // The backend computes the full FRDD extension.
    setState(() => _computedExtension = '${room.roomNumber}${deskNum.toString().padLeft(2, '0')}');
  }

  @override
  Widget build(BuildContext context) {
    final l10n = S.of(context);
    return AlertDialog(
      title: Text(l10n.seatDeskConfig),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            DropdownButtonFormField<int>(
              value: _selectedRoomId,
              decoration: InputDecoration(labelText: l10n.seatRoom),
              items: widget.rooms
                  .map((r) => DropdownMenuItem(
                        value: r.id,
                        child: Text(r.displayName),
                      ))
                  .toList(),
              onChanged: (v) {
                setState(() => _selectedRoomId = v);
                _updateExtension();
              },
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _deskNumberCtrl,
              decoration: InputDecoration(
                labelText: l10n.seatDeskNumber,
                helperText: _computedExtension.isNotEmpty
                    ? 'Ext: $_computedExtension'
                    : null,
              ),
              keyboardType: TextInputType.number,
            ),
            const SizedBox(height: 12),
            SegmentedButton<String>(
              segments: [
                ButtonSegment(value: 'open', label: Text(l10n.seatOpenDesk)),
                ButtonSegment(value: 'designated', label: Text(l10n.seatDesignatedDesk)),
              ],
              selected: {_deskType},
              onSelectionChanged: (v) => setState(() => _deskType = v.first),
            ),
            if (_deskType == 'designated') ...[
              const SizedBox(height: 12),
              TextField(
                controller: _designatedEmailCtrl,
                decoration: InputDecoration(labelText: l10n.seatDesignatedEmail),
                keyboardType: TextInputType.emailAddress,
              ),
            ],
            const SizedBox(height: 12),
            TextField(
              controller: _phoneMacCtrl,
              decoration: const InputDecoration(
                labelText: 'Phone MAC',
                hintText: 'c0:74:ad:xx:xx:xx',
              ),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: Text(l10n.cancel),
        ),
        FilledButton(
          onPressed: _selectedRoomId != null && _deskNumberCtrl.text.isNotEmpty
              ? () {
                  Navigator.pop(context, {
                    'room_id': _selectedRoomId,
                    'desk_number': int.parse(_deskNumberCtrl.text),
                    'desk_type': _deskType,
                    'phone_mac': _phoneMacCtrl.text.isNotEmpty
                        ? _phoneMacCtrl.text
                        : null,
                    'designated_email': _deskType == 'designated'
                        ? _designatedEmailCtrl.text
                        : null,
                    'pos_x': widget.posX,
                    'pos_y': widget.posY,
                  });
                }
              : null,
          child: Text(l10n.save),
        ),
      ],
    );
  }
}
