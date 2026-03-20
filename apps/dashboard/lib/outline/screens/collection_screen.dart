import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shinbee_dashboard/shared/l10n/generated/app_localizations.dart';
import 'package:go_router/go_router.dart';

import '../providers/collections_provider.dart';
import '../providers/documents_provider.dart';
import '../widgets/document_tile.dart';

class CollectionScreen extends ConsumerWidget {
  const CollectionScreen({required this.collectionId, super.key});

  final String collectionId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = S.of(context);
    final collectionAsync = ref.watch(collectionDetailProvider(collectionId));
    final docsAsync = ref.watch(
      documentsListProvider(collectionId),
    );

    final title = collectionAsync.valueOrNull?.name ?? l10n.collections;

    return Scaffold(
      appBar: AppBar(title: Text(title)),
      body: docsAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('${l10n.error}: $e')),
        data: (docs) {
          if (docs.isEmpty) {
            return Center(child: Text(l10n.noResults));
          }
          return ListView.builder(
            itemCount: docs.length,
            itemBuilder: (context, index) {
              final doc = docs[index];
              return DocumentTile(
                document: doc,
                onTap: () => context.go('/wiki/doc/${doc.id}'),
              );
            },
          );
        },
      ),
    );
  }
}
