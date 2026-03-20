class SeatAssignment {
  final int id;
  final int deskId;
  final String employeeEmail;
  final String employeeName;
  final String employeeExtension;
  final String checkedInAt;
  final String? checkedOutAt;

  SeatAssignment({
    required this.id,
    required this.deskId,
    required this.employeeEmail,
    required this.employeeName,
    required this.employeeExtension,
    required this.checkedInAt,
    this.checkedOutAt,
  });

  factory SeatAssignment.fromJson(Map<String, dynamic> json) =>
      SeatAssignment(
        id: json['id'] as int,
        deskId: json['desk_id'] as int,
        employeeEmail: json['employee_email'] as String,
        employeeName: json['employee_name'] as String,
        employeeExtension: json['employee_extension'] as String,
        checkedInAt: json['checked_in_at'] as String,
        checkedOutAt: json['checked_out_at'] as String?,
      );

  bool get isActive => checkedOutAt == null;
}
