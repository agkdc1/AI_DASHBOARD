import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/dashboard_layout.dart';

const _kLayoutKey = 'dashboard_layout';

class LayoutNotifier extends StateNotifier<DashboardLayout> {
  LayoutNotifier() : super(DashboardLayout.defaultLayout) {
    _load();
  }

  Future<void> _load() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_kLayoutKey);
    if (raw != null) {
      try {
        var layout = DashboardLayout.fromJson(
          jsonDecode(raw) as Map<String, dynamic>,
        );
        // Migrate: ensure seating is first in widgetOrder
        final order = List<String>.from(layout.widgetOrder);
        if (order.contains('seating') && order.indexOf('seating') != 0) {
          order.remove('seating');
          order.insert(0, 'seating');
          layout = layout.copyWith(widgetOrder: order);
          // Persist migration
          await prefs.setString(_kLayoutKey, jsonEncode(layout.toJson()));
        }
        state = layout;
      } catch (_) {
        // Corrupted, use defaults
      }
    }
  }

  Future<void> _save() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kLayoutKey, jsonEncode(state.toJson()));
  }

  void toggleWidget(String id, bool visible) {
    final widgets = Set<String>.from(state.visibleWidgets);
    if (visible) {
      widgets.add(id);
    } else {
      widgets.remove(id);
    }
    state = state.copyWith(visibleWidgets: widgets);
    _save();
  }

  void reorder(int oldIndex, int newIndex) {
    final order = List<String>.from(state.widgetOrder);
    if (newIndex > oldIndex) newIndex--;
    final item = order.removeAt(oldIndex);
    order.insert(newIndex, item);
    state = state.copyWith(widgetOrder: order);
    _save();
  }

  void resetToDefaults() {
    state = DashboardLayout.defaultLayout;
    _save();
  }
}

final layoutProvider =
    StateNotifierProvider<LayoutNotifier, DashboardLayout>(
  (ref) => LayoutNotifier(),
);
