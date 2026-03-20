import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';

class MarkdownRenderer extends StatelessWidget {
  const MarkdownRenderer({
    required this.data,
    this.selectable = false,
    super.key,
  });

  final String data;
  final bool selectable;

  @override
  Widget build(BuildContext context) {
    if (selectable) {
      return MarkdownBody(
        data: data,
        selectable: true,
      );
    }
    return Markdown(data: data);
  }
}
