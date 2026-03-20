class Office {
  final int id;
  final String name;
  final String? address;
  final String createdAt;

  Office({
    required this.id,
    required this.name,
    this.address,
    required this.createdAt,
  });

  factory Office.fromJson(Map<String, dynamic> json) => Office(
        id: json['id'] as int,
        name: json['name'] as String,
        address: json['address'] as String?,
        createdAt: json['created_at'] as String,
      );
}

class Floor {
  final int id;
  final int officeId;
  final int floorNumber;
  final String? name;
  final String? floorplanImage;
  final String createdAt;

  Floor({
    required this.id,
    required this.officeId,
    required this.floorNumber,
    this.name,
    this.floorplanImage,
    required this.createdAt,
  });

  factory Floor.fromJson(Map<String, dynamic> json) => Floor(
        id: json['id'] as int,
        officeId: json['office_id'] as int,
        floorNumber: json['floor_number'] as int,
        name: json['name'] as String?,
        floorplanImage: json['floorplan_image'] as String?,
        createdAt: json['created_at'] as String,
      );

  String get displayName => name ?? '${floorNumber}F';
}

class Room {
  final int id;
  final int floorId;
  final int roomNumber;
  final String? name;
  final String createdAt;

  Room({
    required this.id,
    required this.floorId,
    required this.roomNumber,
    this.name,
    required this.createdAt,
  });

  factory Room.fromJson(Map<String, dynamic> json) => Room(
        id: json['id'] as int,
        floorId: json['floor_id'] as int,
        roomNumber: json['room_number'] as int,
        name: json['name'] as String?,
        createdAt: json['created_at'] as String,
      );

  String get displayName => name ?? 'Room $roomNumber';
}

class Desk {
  final int id;
  final int roomId;
  final int deskNumber;
  final String deskExtension;
  final String? phoneMac;
  final String? phoneModel;
  final String? phoneIp;
  final String deskType;
  final String? designatedEmail;
  final double? posX;
  final double? posY;
  final String createdAt;

  Desk({
    required this.id,
    required this.roomId,
    required this.deskNumber,
    required this.deskExtension,
    this.phoneMac,
    this.phoneModel,
    this.phoneIp,
    required this.deskType,
    this.designatedEmail,
    this.posX,
    this.posY,
    required this.createdAt,
  });

  factory Desk.fromJson(Map<String, dynamic> json) => Desk(
        id: json['id'] as int,
        roomId: json['room_id'] as int,
        deskNumber: json['desk_number'] as int,
        deskExtension: json['desk_extension'] as String,
        phoneMac: json['phone_mac'] as String?,
        phoneModel: json['phone_model'] as String?,
        phoneIp: json['phone_ip'] as String?,
        deskType: json['desk_type'] as String,
        designatedEmail: json['designated_email'] as String?,
        posX: (json['pos_x'] as num?)?.toDouble(),
        posY: (json['pos_y'] as num?)?.toDouble(),
        createdAt: json['created_at'] as String,
      );

  bool get isOpen => deskType == 'open';
  bool get isDesignated => deskType == 'designated';
}
