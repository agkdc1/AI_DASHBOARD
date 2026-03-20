import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

import '../models/part.dart';

class PartTile extends StatelessWidget {
  const PartTile({
    required this.part,
    this.onTap,
    super.key,
  });

  final Part part;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: _thumbnail(),
      title: Text(part.name),
      subtitle: Text(
        part.description.isNotEmpty ? part.description : (part.ipn ?? ''),
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
      ),
      trailing: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Text(
            '${part.inStock}',
            style: TextStyle(
              fontWeight: FontWeight.bold,
              color: part.inStock > 0 ? Colors.green : Colors.red,
            ),
          ),
          Text(
            'in stock',
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
      ),
      onTap: onTap,
    );
  }

  Widget _thumbnail() {
    if (part.thumbnail != null && part.thumbnail!.isNotEmpty) {
      return SizedBox(
        width: 40,
        height: 40,
        child: CachedNetworkImage(
          imageUrl: part.thumbnail!,
          fit: BoxFit.cover,
          placeholder: (_, __) => const Icon(Icons.category),
          errorWidget: (_, __, ___) => const Icon(Icons.category),
        ),
      );
    }
    return const SizedBox(
      width: 40,
      height: 40,
      child: Icon(Icons.category),
    );
  }
}
