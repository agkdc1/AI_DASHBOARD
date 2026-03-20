import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shinbee_dashboard/shared/l10n/generated/app_localizations.dart';

import '../api/seating_client.dart';
import '../providers/seating_providers.dart';
import 'floor_editor_screen.dart';

/// Admin screen for managing offices and floors.
class OfficeListScreen extends ConsumerWidget {
  const OfficeListScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = S.of(context);
    final officesAsync = ref.watch(officesProvider);

    return Scaffold(
      appBar: AppBar(title: Text(l10n.seatAdmin)),
      body: officesAsync.when(
        data: (offices) {
          if (offices.isEmpty) {
            return Center(child: Text(l10n.seatNoOffices));
          }
          return ListView.builder(
            itemCount: offices.length,
            itemBuilder: (context, index) {
              final office = offices[index];
              return ExpansionTile(
                leading: const Icon(Icons.business),
                title: Text(office.name),
                subtitle: office.address != null
                    ? Text(office.address!)
                    : null,
                children: [
                  _FloorsList(officeId: office.id),
                ],
              );
            },
          );
        },
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () => _addOffice(context, ref),
        child: const Icon(Icons.add),
      ),
    );
  }

  Future<void> _addOffice(BuildContext context, WidgetRef ref) async {
    final l10n = S.of(context);
    final nameCtrl = TextEditingController();
    final addressCtrl = TextEditingController();

    final result = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(l10n.seatAddOffice),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: nameCtrl,
              decoration: InputDecoration(labelText: l10n.seatOfficeName),
              autofocus: true,
            ),
            const SizedBox(height: 8),
            TextField(
              controller: addressCtrl,
              decoration: InputDecoration(labelText: l10n.seatAddress),
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

    if (result == true && nameCtrl.text.isNotEmpty) {
      final client = ref.read(seatingClientProvider);
      await client.createOffice(
        name: nameCtrl.text,
        address: addressCtrl.text.isNotEmpty ? addressCtrl.text : null,
      );
      ref.invalidate(officesProvider);
    }
  }
}

class _FloorsList extends ConsumerWidget {
  final int officeId;

  const _FloorsList({required this.officeId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = S.of(context);
    final floorsAsync = ref.watch(floorsProvider(officeId));

    return floorsAsync.when(
      data: (floors) {
        return Column(
          children: [
            ...floors.map((floor) => ListTile(
                  contentPadding: const EdgeInsets.only(left: 32),
                  leading: const Icon(Icons.layers),
                  title: Text(floor.displayName),
                  trailing: const Icon(Icons.edit),
                  onTap: () => Navigator.push(
                    context,
                    MaterialPageRoute(
                      builder: (_) =>
                          FloorEditorScreen(floorId: floor.id),
                    ),
                  ),
                )),
            ListTile(
              contentPadding: const EdgeInsets.only(left: 32),
              leading: const Icon(Icons.add, color: Colors.blue),
              title: Text(l10n.seatAddFloor,
                  style: const TextStyle(color: Colors.blue)),
              onTap: () => _addFloor(context, ref),
            ),
          ],
        );
      },
      loading: () => const Padding(
        padding: EdgeInsets.all(16),
        child: Center(child: CircularProgressIndicator()),
      ),
      error: (e, _) => Padding(
        padding: const EdgeInsets.all(16),
        child: Text(e.toString()),
      ),
    );
  }

  Future<void> _addFloor(BuildContext context, WidgetRef ref) async {
    final l10n = S.of(context);
    final numberCtrl = TextEditingController();
    final nameCtrl = TextEditingController();

    final result = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(l10n.seatAddFloor),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: numberCtrl,
              decoration: InputDecoration(labelText: l10n.seatFloorNumber),
              keyboardType: TextInputType.number,
            ),
            const SizedBox(height: 8),
            TextField(
              controller: nameCtrl,
              decoration: InputDecoration(labelText: l10n.seatFloorName),
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
      await client.createFloor(
        officeId: officeId,
        floorNumber: int.parse(numberCtrl.text),
        name: nameCtrl.text.isNotEmpty ? nameCtrl.text : null,
      );
      ref.invalidate(floorsProvider(officeId));
    }
  }
}
