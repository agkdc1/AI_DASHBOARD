class Company {
  const Company({
    required this.pk,
    required this.name,
    this.description = '',
    this.website,
    this.phone,
    this.email,
    this.isSupplier = false,
    this.isManufacturer = false,
    this.isCustomer = false,
    this.active = true,
    this.image,
    this.thumbnail,
  });

  final int pk;
  final String name;
  final String description;
  final String? website;
  final String? phone;
  final String? email;
  final bool isSupplier;
  final bool isManufacturer;
  final bool isCustomer;
  final bool active;
  final String? image;
  final String? thumbnail;

  factory Company.fromJson(Map<String, dynamic> json) => Company(
        pk: json['pk'] as int,
        name: json['name'] as String,
        description: json['description'] as String? ?? '',
        website: json['website'] as String?,
        phone: json['phone'] as String?,
        email: json['email'] as String?,
        isSupplier: json['is_supplier'] as bool? ?? false,
        isManufacturer: json['is_manufacturer'] as bool? ?? false,
        isCustomer: json['is_customer'] as bool? ?? false,
        active: json['active'] as bool? ?? true,
        image: json['image'] as String?,
        thumbnail: json['thumbnail'] as String?,
      );
}
