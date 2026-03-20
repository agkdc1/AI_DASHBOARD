import 'package:flutter/material.dart';

import '../models/collection.dart';

class CollectionTile extends StatelessWidget {
  const CollectionTile({
    required this.collection,
    this.onTap,
    super.key,
  });

  final OutlineCollection collection;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: collection.icon != null && collection.icon!.isNotEmpty
          ? Text(collection.icon!, style: const TextStyle(fontSize: 24))
          : const Icon(Icons.folder),
      title: Text(collection.name),
      subtitle: collection.description.isNotEmpty
          ? Text(
              collection.description,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            )
          : null,
      trailing: const Icon(Icons.chevron_right),
      onTap: onTap,
    );
  }
}
