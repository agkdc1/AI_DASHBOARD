class DashboardLayout {
  final Set<String> visibleWidgets;
  final List<String> widgetOrder;

  const DashboardLayout({
    required this.visibleWidgets,
    required this.widgetOrder,
  });

  static const defaultLayout = DashboardLayout(
    visibleWidgets: {
      'inventory',
      'tasks',
      'wiki',
      'voice_request',
      'call_request',
      'rakuten',
      'picking_list',
      'seating',
      'pbx',
      'staff',
      'fax_review',
    },
    widgetOrder: [
      'seating',
      'inventory',
      'tasks',
      'wiki',
      'voice_request',
      'call_request',
      'rakuten',
      'picking_list',
      'pbx',
      'staff',
      'fax_review',
    ],
  );

  DashboardLayout copyWith({
    Set<String>? visibleWidgets,
    List<String>? widgetOrder,
  }) {
    return DashboardLayout(
      visibleWidgets: visibleWidgets ?? this.visibleWidgets,
      widgetOrder: widgetOrder ?? this.widgetOrder,
    );
  }

  Map<String, dynamic> toJson() => {
        'visibleWidgets': visibleWidgets.toList(),
        'widgetOrder': widgetOrder,
      };

  factory DashboardLayout.fromJson(Map<String, dynamic> json) {
    return DashboardLayout(
      visibleWidgets: Set<String>.from(json['visibleWidgets'] as List),
      widgetOrder: List<String>.from(json['widgetOrder'] as List),
    );
  }
}
