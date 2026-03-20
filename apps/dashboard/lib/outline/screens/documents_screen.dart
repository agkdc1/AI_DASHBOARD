import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shinbee_dashboard/shared/l10n/generated/app_localizations.dart';
import 'package:go_router/go_router.dart';

import '../providers/documents_provider.dart';
import '../providers/collections_provider.dart';
import '../widgets/document_tile.dart';
import '../widgets/collection_tile.dart';

class DocumentsScreen extends ConsumerWidget {
  const DocumentsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = S.of(context);
    final docsAsync = ref.watch(documentsListProvider(null));
    final collectionsAsync = ref.watch(collectionsListProvider);

    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.tabWiki),
        actions: [
          IconButton(
            icon: const Icon(Icons.search),
            onPressed: () => context.go('/wiki/search'),
          ),
        ],
      ),
      body: ListView(
        children: [
          // Collections section
          collectionsAsync.when(
            loading: () => const LinearProgressIndicator(),
            error: (_, __) => const SizedBox.shrink(),
            data: (collections) {
              if (collections.isEmpty) return const SizedBox.shrink();
              return Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
                    child: Text(
                      l10n.collections,
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                  ),
                  ...collections.map((c) => CollectionTile(
                        collection: c,
                        onTap: () => context.go('/wiki/collection/${c.id}'),
                      )),
                  const Divider(),
                ],
              );
            },
          ),
          // Recent documents section
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
            child: Text(
              l10n.documents,
              style: Theme.of(context).textTheme.titleMedium,
            ),
          ),
          docsAsync.when(
            loading: () => const Center(
              child: Padding(
                padding: EdgeInsets.all(32),
                child: CircularProgressIndicator(),
              ),
            ),
            error: (e, _) => Center(child: Text('${l10n.error}: $e')),
            data: (docs) {
              if (docs.isEmpty) {
                return Center(
                  child: Padding(
                    padding: const EdgeInsets.all(32),
                    child: Text(l10n.noResults),
                  ),
                );
              }
              return Column(
                children: docs
                    .map((doc) => DocumentTile(
                          document: doc,
                          onTap: () => context.go('/wiki/doc/${doc.id}'),
                        ))
                    .toList(),
              );
            },
          ),
        ],
      ),
    );
  }
}
