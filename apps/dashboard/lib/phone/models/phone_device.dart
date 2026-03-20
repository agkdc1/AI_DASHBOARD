/// Phone device from provisioning data.
class PhoneDevice {
  const PhoneDevice({
    required this.mac,
    required this.type,
    this.name = '',
    this.extension = '',
  });

  final String mac;
  final String type;
  final String name;
  final String extension;

  factory PhoneDevice.fromJson(Map<String, dynamic> json) => PhoneDevice(
        mac: json['mac'] as String? ?? '',
        type: json['type'] as String? ?? '',
        name: json['name'] as String? ?? '',
        extension: json['extension'] as String? ?? '',
      );

  bool get isFixed => type == 'fixed';
  bool get isHotdesk => type == 'hotdesk';
}
