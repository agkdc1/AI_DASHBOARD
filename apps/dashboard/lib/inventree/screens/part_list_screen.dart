import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shinbee_dashboard/shared/l10n/generated/app_localizations.dart';
import 'package:go_router/go_router.dart';

import '../providers/parts_provider.dart';
import '../widgets/part_tile.dart';
import '../widgets/search_bar.dart';

class PartListScreen extends ConsumerStatefulWidget {
  const PartListScreen({super.key});

  @override
  ConsumerState<PartListScreen> createState() => _PartListScreenState();
}

class _PartListScreenState extends ConsumerState<PartListScreen> {
  String _search = '';

  @override
  Widget build(BuildContext context) {
    final l10n = S.of(context);
    final partsAsync = ref.watch(
      partsListProvider(_search.isEmpty ? null : _search),
    );

    return Scaffold(
      appBar: AppBar(title: Text(l10n.parts)),
      body: Column(
        children: [
          InvenTreeSearchBar(
            onChanged: (v) => setState(() => _search = v),
          ),
          Expanded(
            child: partsAsync.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => Center(child: Text('${l10n.error}: $e')),
              data: (parts) {
                if (parts.isEmpty) {
                  return Center(child: Text(l10n.noResults));
                }
                return ListView.builder(
                  itemCount: parts.length,
                  itemBuilder: (context, index) {
                    final part = parts[index];
                    return PartTile(
                      part: part,
                      onTap: () =>
                          context.go('/inventory/parts/${part.pk}'),
                    );
                  },
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}
