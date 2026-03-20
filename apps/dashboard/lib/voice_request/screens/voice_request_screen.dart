import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_tabler_icons/flutter_tabler_icons.dart';
import 'package:shinbee_dashboard/shared/l10n/generated/app_localizations.dart';

class VoiceRequestScreen extends ConsumerStatefulWidget {
  const VoiceRequestScreen({super.key});

  @override
  ConsumerState<VoiceRequestScreen> createState() =>
      _VoiceRequestScreenState();
}

class _VoiceRequestScreenState extends ConsumerState<VoiceRequestScreen> {
  String? _targetEmail;
  bool _recording = false;
  Map<String, dynamic>? _preview;
  bool _submitting = false;

  @override
  Widget build(BuildContext context) {
    final l10n = S.of(context);

    return Scaffold(
      appBar: AppBar(title: Text(l10n.voiceRequest)),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: _preview != null ? _buildPreview(l10n) : _buildRecorder(l10n),
      ),
    );
  }

  Widget _buildRecorder(S l10n) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        TextField(
          decoration: InputDecoration(
            labelText: l10n.voiceTargetEmail,
            border: const OutlineInputBorder(),
          ),
          onChanged: (v) => _targetEmail = v,
        ),
        const SizedBox(height: 24),
        Expanded(
          child: Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(
                  _recording ? TablerIcons.player_stop : TablerIcons.microphone,
                  size: 80,
                  color: _recording ? Colors.red : Theme.of(context).colorScheme.primary,
                ),
                const SizedBox(height: 16),
                Text(
                  _recording ? l10n.voiceRecording : l10n.voiceTapToRecord,
                  style: Theme.of(context).textTheme.titleLarge,
                ),
              ],
            ),
          ),
        ),
        FilledButton.icon(
          onPressed: _recording ? _stopRecording : _startRecording,
          icon: Icon(_recording ? TablerIcons.player_stop : TablerIcons.microphone),
          label: Text(_recording ? l10n.voiceStop : l10n.voiceStart),
        ),
      ],
    );
  }

  Widget _buildPreview(S l10n) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(l10n.voicePreviewTitle,
                    style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 8),
                Text('${l10n.voiceTaskTitle}: ${_preview!['title'] ?? ''}'),
                const SizedBox(height: 4),
                Text('${l10n.voiceDescription}: ${_preview!['description'] ?? ''}'),
                if (_preview!['due_date'] != null) ...[
                  const SizedBox(height: 4),
                  Text('${l10n.voiceDueDate}: ${_preview!['due_date']}'),
                ],
              ],
            ),
          ),
        ),
        const Spacer(),
        Row(
          children: [
            Expanded(
              child: OutlinedButton(
                onPressed: () => setState(() => _preview = null),
                child: Text(l10n.cancel),
              ),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: FilledButton(
                onPressed: _submitting ? null : _confirmRequest,
                child: _submitting
                    ? const SizedBox(
                        height: 20, width: 20,
                        child: CircularProgressIndicator(strokeWidth: 2))
                    : Text(l10n.voiceConfirm),
              ),
            ),
          ],
        ),
      ],
    );
  }

  void _startRecording() {
    setState(() => _recording = true);
    // TODO: Integrate platform audio recording
  }

  void _stopRecording() {
    setState(() {
      _recording = false;
      // Placeholder — in production, send audio to AI assistant
      _preview = {
        'title': '音声依頼',
        'description': '録音された依頼内容がここに表示されます',
        'due_date': null,
        'priority': 2,
      };
    });
  }

  Future<void> _confirmRequest() async {
    setState(() => _submitting = true);
    // TODO: POST to /voice-request/{id}/confirm
    await Future.delayed(const Duration(seconds: 1));
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Task created')),
      );
      setState(() {
        _submitting = false;
        _preview = null;
      });
    }
  }
}
