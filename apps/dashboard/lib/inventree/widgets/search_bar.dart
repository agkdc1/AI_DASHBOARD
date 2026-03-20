import 'package:flutter/material.dart';
import 'package:shinbee_dashboard/shared/l10n/generated/app_localizations.dart';

class InvenTreeSearchBar extends StatelessWidget {
  const InvenTreeSearchBar({
    required this.onChanged,
    this.onSubmitted,
    this.controller,
    super.key,
  });

  final ValueChanged<String> onChanged;
  final ValueChanged<String>? onSubmitted;
  final TextEditingController? controller;

  @override
  Widget build(BuildContext context) {
    final l10n = S.of(context);
    return Padding(
      padding: const EdgeInsets.all(8),
      child: TextField(
        controller: controller,
        decoration: InputDecoration(
          hintText: l10n.search,
          prefixIcon: const Icon(Icons.search),
          isDense: true,
        ),
        onChanged: onChanged,
        onSubmitted: onSubmitted,
      ),
    );
  }
}
