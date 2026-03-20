import 'package:flutter/material.dart';

import '../models/document.dart';

class DocumentTile extends StatelessWidget {
  const DocumentTile({
    required this.document,
    this.onTap,
    super.key,
  });

  final OutlineDocument document;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: document.emoji != null && document.emoji!.isNotEmpty
          ? Text(document.emoji!, style: const TextStyle(fontSize: 24))
          : const Icon(Icons.article),
      title: Text(document.title),
      subtitle: document.updatedAt != null
          ? Text(
              'Updated ${document.updatedAt!.substring(0, 10)}',
              style: Theme.of(context).textTheme.bodySmall,
            )
          : null,
      trailing: const Icon(Icons.chevron_right),
      onTap: onTap,
    );
  }
}
