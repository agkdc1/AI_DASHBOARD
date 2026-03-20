/// A registered staff member with their deny rules.
class StaffMember {
  final String email;
  final String displayName;
  final String? photoUrl;
  final String role;
  final List<String> deniedPermissions;
  final String? createdAt;
  final String? updatedAt;

  const StaffMember({
    required this.email,
    required this.displayName,
    this.photoUrl,
    required this.role,
    this.deniedPermissions = const [],
    this.createdAt,
    this.updatedAt,
  });

  factory StaffMember.fromJson(Map<String, dynamic> json) {
    return StaffMember(
      email: json['email'] as String,
      displayName: json['display_name'] as String,
      photoUrl: json['photo_url'] as String?,
      role: json['role'] as String,
      deniedPermissions: (json['denied_permissions'] as List?)
              ?.cast<String>() ??
          const [],
      createdAt: json['created_at'] as String?,
      updatedAt: json['updated_at'] as String?,
    );
  }
}

/// Permission definition from the backend.
class PermissionDef {
  final String id;
  final String labelEn;
  final String labelJa;
  final String labelKo;
  final String category;

  const PermissionDef({
    required this.id,
    required this.labelEn,
    required this.labelJa,
    required this.labelKo,
    required this.category,
  });

  factory PermissionDef.fromJson(Map<String, dynamic> json) {
    return PermissionDef(
      id: json['id'] as String,
      labelEn: json['label_en'] as String,
      labelJa: json['label_ja'] as String,
      labelKo: json['label_ko'] as String,
      category: json['category'] as String,
    );
  }

  String label(String locale) {
    switch (locale) {
      case 'ja':
        return labelJa;
      case 'ko':
        return labelKo;
      default:
        return labelEn;
    }
  }
}

/// The current user's IAM profile.
class IamProfile {
  final bool registered;
  final String role;
  final List<String> denied;
  final List<String> allPermissions;

  const IamProfile({
    required this.registered,
    required this.role,
    this.denied = const [],
    this.allPermissions = const [],
  });

  factory IamProfile.fromJson(Map<String, dynamic> json) {
    return IamProfile(
      registered: json['registered'] as bool? ?? false,
      role: json['role'] as String? ?? 'guest',
      denied:
          (json['denied'] as List?)?.cast<String>() ?? const [],
      allPermissions:
          (json['all_permissions'] as List?)?.cast<String>() ?? const [],
    );
  }

  bool isAllowed(String permission) => allPermissions.contains(permission);
}
