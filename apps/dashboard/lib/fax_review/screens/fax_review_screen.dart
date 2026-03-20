import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_tabler_icons/flutter_tabler_icons.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:shinbee_dashboard/shared/l10n/generated/app_localizations.dart';

import '../api/fax_review_client.dart';

class FaxReviewScreen extends ConsumerStatefulWidget {
  const FaxReviewScreen({super.key});

  @override
  ConsumerState<FaxReviewScreen> createState() => _FaxReviewScreenState();
}

class _FaxReviewScreenState extends ConsumerState<FaxReviewScreen> {
  List<Map<String, dynamic>> _faxes = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadFaxes();
  }

  Future<void> _loadFaxes() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final client = ref.read(faxReviewClientProvider);
      final result = await client.listPending();
      setState(() {
        _faxes = result;
        _loading = false;
      });
    } catch (e) {
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  Future<void> _approve(Map<String, dynamic> fax) async {
    final l10n = S.of(context);
    try {
      final client = ref.read(faxReviewClientProvider);
      await client.approve(
        docId: fax['doc_id'] as String?,
        pdfId: fax['pdf_id'] as String?,
      );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(l10n.faxApproved)),
        );
        _loadFaxes();
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error: $e')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = S.of(context);

    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.faxReview),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(_error!, style: const TextStyle(color: Colors.red)),
                      const SizedBox(height: 16),
                      ElevatedButton(
                        onPressed: _loadFaxes,
                        child: Text(l10n.retry),
                      ),
                    ],
                  ),
                )
              : _faxes.isEmpty
                  ? Center(
                      child: Text(
                        l10n.faxReviewEmpty,
                        style: Theme.of(context).textTheme.bodyLarge,
                      ),
                    )
                  : RefreshIndicator(
                      onRefresh: _loadFaxes,
                      child: ListView.builder(
                        padding: const EdgeInsets.all(16),
                        itemCount: _faxes.length,
                        itemBuilder: (context, index) =>
                            _buildFaxCard(_faxes[index]),
                      ),
                    ),
    );
  }

  Widget _buildFaxCard(Map<String, dynamic> fax) {
    final l10n = S.of(context);
    final name = fax['name'] as String? ?? '';
    final createdTime = fax['created_time'] as String?;
    final pdfUrl = fax['pdf_url'] as String?;
    final docUrl = fax['doc_url'] as String?;

    String subtitle = '';
    if (createdTime != null) {
      final dt = DateTime.tryParse(createdTime);
      if (dt != null) {
        subtitle =
            '${dt.year}-${dt.month.toString().padLeft(2, '0')}-${dt.day.toString().padLeft(2, '0')} '
            '${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
      }
    }

    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(name, style: Theme.of(context).textTheme.titleMedium),
            if (subtitle.isNotEmpty) ...[
              const SizedBox(height: 4),
              Text(subtitle, style: Theme.of(context).textTheme.bodySmall),
            ],
            const SizedBox(height: 12),
            Row(
              children: [
                if (pdfUrl != null)
                  IconButton(
                    icon: const Icon(TablerIcons.file_type_pdf, color: Colors.red),
                    tooltip: l10n.faxViewPdf,
                    onPressed: () => launchUrl(Uri.parse(pdfUrl)),
                  ),
                if (docUrl != null)
                  IconButton(
                    icon: const Icon(TablerIcons.file_text, color: Colors.blue),
                    tooltip: l10n.faxEditDoc,
                    onPressed: () => launchUrl(Uri.parse(docUrl)),
                  ),
                const Spacer(),
                FilledButton.icon(
                  icon: const Icon(TablerIcons.check),
                  label: Text(l10n.faxApprove),
                  onPressed: () => _approve(fax),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
