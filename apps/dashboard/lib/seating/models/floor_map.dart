import 'office.dart';
import 'seat_assignment.dart';

class DeskWithStatus {
  final Desk desk;
  final SeatAssignment? currentAssignment;

  DeskWithStatus({required this.desk, this.currentAssignment});

  factory DeskWithStatus.fromJson(Map<String, dynamic> json) => DeskWithStatus(
        desk: Desk.fromJson(json['desk'] as Map<String, dynamic>),
        currentAssignment: json['current_assignment'] != null
            ? SeatAssignment.fromJson(
                json['current_assignment'] as Map<String, dynamic>)
            : null,
      );

  bool get isOccupied => currentAssignment != null;
  bool get isOpen => !isOccupied && desk.isOpen;

  bool isAvailableFor(String email) {
    if (isOccupied) return false;
    if (desk.isDesignated && desk.designatedEmail != email) return false;
    return true;
  }

  bool isMyDesignated(String email) =>
      desk.isDesignated && desk.designatedEmail == email;
}

class FloorMap {
  final Floor floor;
  final List<DeskWithStatus> desks;

  FloorMap({required this.floor, required this.desks});

  factory FloorMap.fromJson(Map<String, dynamic> json) => FloorMap(
        floor: Floor.fromJson(json['floor'] as Map<String, dynamic>),
        desks: (json['desks'] as List)
            .map((e) => DeskWithStatus.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}
