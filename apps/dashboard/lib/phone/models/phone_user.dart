/// LDAP phonebook user.
class PhoneUser {
  const PhoneUser({
    required this.uid,
    required this.cn,
    this.telephoneNumber = '',
    this.dn = '',
  });

  final String uid;
  final String cn;
  final String telephoneNumber;
  final String dn;

  factory PhoneUser.fromJson(Map<String, dynamic> json) => PhoneUser(
        uid: json['uid'] as String? ?? '',
        cn: json['cn'] as String? ?? '',
        telephoneNumber: json['telephoneNumber'] as String? ?? '',
        dn: json['dn'] as String? ?? '',
      );
}
