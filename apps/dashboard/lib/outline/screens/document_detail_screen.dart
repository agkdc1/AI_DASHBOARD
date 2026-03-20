import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shinbee_dashboard/shared/l10n/generated/app_localizations.dart';
import 'package:go_router/go_router.dart';

import '../providers/documents_provider.dart';
import '../widgets/markdown_renderer.dart';

class DocumentDetailScreen extends ConsumerWidget {
  const DocumentDetailScreen({required this.documentId, super.key});

  final String documentId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = S.of(context);
    final docAsync = ref.watch(documentDetailProvider(documentId));

    return docAsync.when(
      loading: () => Scaffold(
        appBar: AppBar(),
        body: const Center(child: CircularProgressIndicator()),
      ),
      error: (e, _) => Scaffold(
        appBar: AppBar(),
        body: Center(child: Text('${l10n.error}: $e')),
      ),
      data: (doc) => Scaffold(
        appBar: AppBar(
          title: Text(doc.title),
          actions: [
            IconButton(
              icon: const Icon(Icons.edit),
              onPressed: () => context.go('/wiki/doc/$documentId/edit'),
            ),
          ],
        ),
        body: MarkdownRenderer(
          data: doc.text,
          selectable: true,
        ),
      ),
    );
  }
}
