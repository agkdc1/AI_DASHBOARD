import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shinbee_dashboard/shared/l10n/generated/app_localizations.dart';

import '../api/outline_client.dart';
import '../providers/documents_provider.dart';

class EditorScreen extends ConsumerStatefulWidget {
  const EditorScreen({required this.documentId, super.key});

  final String documentId;

  @override
  ConsumerState<EditorScreen> createState() => _EditorScreenState();
}

class _EditorScreenState extends ConsumerState<EditorScreen> {
  final _controller = TextEditingController();
  bool _saving = false;
  bool _loaded = false;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    try {
      final client = ref.read(outlineClientProvider);
      await client.updateDocument(
        id: widget.documentId,
        text: _controller.text,
      );
      ref.invalidate(documentDetailProvider(widget.documentId));
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Saved')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = S.of(context);
    final docAsync = ref.watch(documentDetailProvider(widget.documentId));

    return docAsync.when(
      loading: () => Scaffold(
        appBar: AppBar(title: Text(l10n.editDocument)),
        body: const Center(child: CircularProgressIndicator()),
      ),
      error: (e, _) => Scaffold(
        appBar: AppBar(title: Text(l10n.editDocument)),
        body: Center(child: Text('${l10n.error}: $e')),
      ),
      data: (doc) {
        if (!_loaded) {
          _controller.text = doc.text;
          _loaded = true;
        }
        return Scaffold(
          appBar: AppBar(
            title: Text(doc.title),
            actions: [
              if (_saving)
                const Padding(
                  padding: EdgeInsets.all(16),
                  child: SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  ),
                )
              else
                IconButton(
                  icon: const Icon(Icons.save),
                  onPressed: _save,
                ),
            ],
          ),
          body: Padding(
            padding: const EdgeInsets.all(16),
            child: TextField(
              controller: _controller,
              maxLines: null,
              expands: true,
              textAlignVertical: TextAlignVertical.top,
              decoration: const InputDecoration(
                border: InputBorder.none,
                hintText: 'Write markdown...',
              ),
              style: const TextStyle(fontFamily: 'monospace'),
            ),
          ),
        );
      },
    );
  }
}
