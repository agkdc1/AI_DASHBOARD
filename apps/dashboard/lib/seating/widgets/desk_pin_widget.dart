import 'package:flutter/material.dart';

import '../models/floor_map.dart';

/// Individual desk marker on the floor plan.
class DeskPinWidget extends StatelessWidget {
  final DeskWithStatus deskStatus;
  final String? currentUserEmail;
  final VoidCallback? onTap;
  final bool showLabel;

  const DeskPinWidget({
    super.key,
    required this.deskStatus,
    this.currentUserEmail,
    this.onTap,
    this.showLabel = true,
  });

  Color get _pinColor {
    if (deskStatus.isOccupied) {
      // Check if occupied by current user
      if (currentUserEmail != null &&
          deskStatus.currentAssignment?.employeeEmail == currentUserEmail) {
        return Colors.amber;
      }
      return Colors.red;
    }
    if (currentUserEmail != null && deskStatus.isMyDesignated(currentUserEmail!)) {
      return Colors.blue;
    }
    if (deskStatus.desk.isDesignated) {
      return Colors.grey;
    }
    return Colors.green;
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 20,
            height: 20,
            decoration: BoxDecoration(
              color: _pinColor,
              shape: BoxShape.circle,
              border: Border.all(color: Colors.white, width: 2),
              boxShadow: const [
                BoxShadow(color: Colors.black26, blurRadius: 3, offset: Offset(0, 1)),
              ],
            ),
            child: Center(
              child: Text(
                deskStatus.desk.deskExtension.length > 2
                    ? deskStatus.desk.deskExtension.substring(
                        deskStatus.desk.deskExtension.length - 2)
                    : deskStatus.desk.deskExtension,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 8,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ),
          ),
          if (showLabel && deskStatus.isOccupied)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 1),
              decoration: BoxDecoration(
                color: Colors.black54,
                borderRadius: BorderRadius.circular(4),
              ),
              child: Text(
                deskStatus.currentAssignment!.employeeName,
                style: const TextStyle(color: Colors.white, fontSize: 8),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
        ],
      ),
    );
  }
}
