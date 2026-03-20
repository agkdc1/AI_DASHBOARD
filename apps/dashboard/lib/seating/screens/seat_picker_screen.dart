import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:shinbee_dashboard/shared/l10n/generated/app_localizations.dart';

import '../../app/auth/auth_state.dart';
import '../../app/auth/token_manager.dart';
import '../api/seating_client.dart';
import '../models/floor_map.dart';
import '../models/seat_assignment.dart';
import '../providers/seating_providers.dart';
import '../widgets/floor_plan_widget.dart';

/// User-facing seat selection screen with floor plan and desk pins.
class SeatPickerScreen extends ConsumerStatefulWidget {
  const SeatPickerScreen({super.key});

  @override
  ConsumerState<SeatPickerScreen> createState() => _SeatPickerScreenState();
}

class _SeatPickerScreenState extends ConsumerState<SeatPickerScreen> {
  int? _selectedFloorId;
  // Track active assignment locally for immediate UI update after check-in.
  // Cleared once the provider catches up or on checkout.
  SeatAssignment? _localAssignment;

  void _setLocalAssignment(SeatAssignment? a) {
    if (mounted) setState(() => _localAssignment = a);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = S.of(context);
    final officesAsync = ref.watch(officesProvider);
    final myAssignment = ref.watch(myAssignmentProvider);
    final authState = ref.watch(tokenManagerProvider);
    final email = authState is Authenticated ? authState.email : '';

    // Sync local assignment with provider once provider catches up
    final providerAssignment = myAssignment.valueOrNull;
    final effectiveAssignment = _localAssignment ?? providerAssignment;

    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.seatManagement),
        actions: [
          IconButton(
            icon: const Icon(Icons.person_pin),
            tooltip: l10n.seatMySeat,
            onPressed: () => context.go('/home/seating/my-seat'),
          ),
          // Refresh button
          IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: l10n.seatRefresh,
            onPressed: () {
              ref.invalidate(myAssignmentProvider);
              if (_selectedFloorId != null) {
                ref.invalidate(floorMapProvider(_selectedFloorId!));
              }
              setState(() => _localAssignment = null);
            },
          ),
          IconButton(
            icon: const Icon(Icons.settings),
            tooltip: l10n.seatAdmin,
            onPressed: () => context.go('/home/seating/admin'),
          ),
        ],
      ),
      body: officesAsync.when(
        data: (offices) {
          if (offices.isEmpty) {
            return Center(child: Text(l10n.seatNoOffices));
          }

          return Column(
            children: [
              _FloorSelector(
                offices: offices,
                selectedFloorId: _selectedFloorId,
                onFloorSelected: (id) => setState(() => _selectedFloorId = id),
              ),
              // Current assignment banner
              if (effectiveAssignment != null)
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.symmetric(
                      horizontal: 16, vertical: 8),
                  color: Colors.amber.shade100,
                  child: Row(
                    children: [
                      const Icon(Icons.check_circle,
                          color: Colors.green, size: 20),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          '${l10n.seatCheckedIn}: ${effectiveAssignment.employeeName} (Ext ${effectiveAssignment.employeeExtension})',
                          style: const TextStyle(fontSize: 13),
                        ),
                      ),
                      TextButton(
                        onPressed: () => _checkOut(ref, email),
                        child: Text(l10n.seatCheckOut),
                      ),
                    ],
                  ),
                ),
              // Floor map
              Expanded(
                child: _selectedFloorId != null
                    ? _FloorMapView(
                        floorId: _selectedFloorId!,
                        userEmail: email,
                        onCheckIn: (assignment) {
                          _setLocalAssignment(assignment);
                          ref.invalidate(myAssignmentProvider);
                          ref.invalidate(floorMapProvider(_selectedFloorId!));
                        },
                      )
                    : Center(child: Text(l10n.seatSelectFloor)),
              ),
            ],
          );
        },
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
      ),
    );
  }

  Future<void> _checkOut(WidgetRef ref, String email) async {
    final client = ref.read(seatingClientProvider);
    try {
      await client.checkOut();
      setState(() => _localAssignment = null);
      ref.invalidate(myAssignmentProvider);
      if (_selectedFloorId != null) {
        ref.invalidate(floorMapProvider(_selectedFloorId!));
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.toString())));
      }
    }
  }
}

class _FloorSelector extends ConsumerWidget {
  final List offices;
  final int? selectedFloorId;
  final ValueChanged<int> onFloorSelected;

  const _FloorSelector({
    required this.offices,
    required this.selectedFloorId,
    required this.onFloorSelected,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final floorWidgets = <Widget>[];
    for (final office in offices) {
      final floorsAsync = ref.watch(floorsProvider(office.id));
      floorsAsync.whenData((floors) {
        for (final floor in floors) {
          floorWidgets.add(
            ChoiceChip(
              label: Text(floor.displayName),
              selected: selectedFloorId == floor.id,
              onSelected: (_) => onFloorSelected(floor.id),
            ),
          );
        }
      });
    }

    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Row(
        children: floorWidgets.isEmpty
            ? [const Text('No floors')]
            : floorWidgets
                .expand((w) => [w, const SizedBox(width: 8)])
                .toList(),
      ),
    );
  }
}

class _FloorMapView extends ConsumerWidget {
  final int floorId;
  final String userEmail;
  final void Function(SeatAssignment assignment)? onCheckIn;

  const _FloorMapView({
    required this.floorId,
    required this.userEmail,
    this.onCheckIn,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = S.of(context);
    final mapAsync = ref.watch(floorMapProvider(floorId));
    final client = ref.read(seatingClientProvider);

    return mapAsync.when(
      data: (floorMap) {
        final floorplanUrl = floorMap.floor.floorplanImage != null
            ? client.getFloorplanUrl(floorId)
            : null;

        return FloorPlanWidget(
          floorplanUrl: floorplanUrl,
          desks: floorMap.desks,
          currentUserEmail: userEmail,
          onTapDesk: (deskStatus) {
            _showDeskBottomSheet(context, ref, deskStatus, l10n);
          },
        );
      },
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(child: Text(e.toString())),
    );
  }

  void _showDeskBottomSheet(
    BuildContext context,
    WidgetRef ref,
    DeskWithStatus deskStatus,
    S l10n,
  ) {
    final desk = deskStatus.desk;
    final canCheckIn = deskStatus.isAvailableFor(userEmail);

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
            if (deskStatus.isOccupied) ...[
              Row(
                children: [
                  const Icon(Icons.person, size: 16, color: Colors.red),
                  const SizedBox(width: 4),
                  Text(
                    '${l10n.seatOccupiedBy}: ${deskStatus.currentAssignment!.employeeName}',
                  ),
                ],
              ),
            ] else ...[
              Row(
                children: [
                  const Icon(Icons.check_circle, size: 16, color: Colors.green),
                  const SizedBox(width: 4),
                  Text(l10n.seatAvailable),
                ],
              ),
            ],
            if (desk.isDesignated && desk.designatedEmail != null)
              Text('${l10n.seatDesignatedFor}: ${desk.designatedEmail}'),
            const SizedBox(height: 16),
            if (canCheckIn)
              SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                  onPressed: () async {
                    Navigator.pop(ctx);
                    final client = ref.read(seatingClientProvider);
                    try {
                      final assignment = await client.checkIn(desk.id);
                      // Notify parent for immediate banner update
                      onCheckIn?.call(assignment);
                    } catch (e) {
                      if (context.mounted) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(content: Text(e.toString())),
                        );
                      }
                    }
                  },
                  icon: const Icon(Icons.login),
                  label: Text(l10n.seatCheckIn),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
