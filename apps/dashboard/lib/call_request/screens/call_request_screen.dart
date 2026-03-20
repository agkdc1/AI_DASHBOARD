import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_tabler_icons/flutter_tabler_icons.dart';
import 'package:shinbee_dashboard/call_request/api/call_request_client.dart';
import 'package:shinbee_dashboard/shared/l10n/generated/app_localizations.dart';

class CallRequestScreen extends ConsumerStatefulWidget {
  const CallRequestScreen({super.key});

  @override
  ConsumerState<CallRequestScreen> createState() => _CallRequestScreenState();
}

class _CallRequestScreenState extends ConsumerState<CallRequestScreen> {
  final _callerExtCtrl = TextEditingController();
  final _targetExtCtrl = TextEditingController();
  String _status = 'idle'; // idle, ringing, in_progress, analyzing, preview
  String? _callId;
  Map<String, dynamic>? _analysis;
  String? _error;
  bool _confirming = false;

  @override
  void dispose() {
    _callerExtCtrl.dispose();
    _targetExtCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = S.of(context);

    return Scaffold(
      appBar: AppBar(title: Text(l10n.callRequest)),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: _analysis != null ? _buildAnalysis(l10n) : _buildDialer(l10n),
      ),
    );
  }

  Widget _buildDialer(S l10n) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        TextField(
          controller: _callerExtCtrl,
          decoration: InputDecoration(
            labelText: l10n.callCallerExtension,
            border: const OutlineInputBorder(),
            prefixIcon: const Icon(TablerIcons.user),
          ),
          keyboardType: TextInputType.number,
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _targetExtCtrl,
          decoration: InputDecoration(
            labelText: l10n.callTargetExtension,
            border: const OutlineInputBorder(),
            prefixIcon: const Icon(TablerIcons.phone),
          ),
          keyboardType: TextInputType.number,
        ),
        if (_error != null) ...[
          const SizedBox(height: 12),
          Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
        ],
        const SizedBox(height: 24),
        Expanded(
          child: Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                if (_status == 'ringing' || _status == 'analyzing')
                  const CircularProgressIndicator()
                else
                  Icon(
                    _status == 'idle'
                        ? TablerIcons.phone_call
                        : TablerIcons.phone_incoming,
                    size: 80,
                    color: _status == 'idle'
                        ? Theme.of(context).colorScheme.primary
                        : Colors.green,
                  ),
                const SizedBox(height: 16),
                Text(
                  _statusText(l10n),
                  style: Theme.of(context).textTheme.titleLarge,
                ),
              ],
            ),
          ),
        ),
        if (_status == 'idle')
          FilledButton.icon(
            onPressed: _initiateCall,
            icon: const Icon(TablerIcons.phone_call),
            label: Text(l10n.callStart),
          )
        else if (_status == 'in_progress')
          FilledButton.icon(
            onPressed: _analyzeCall,
            icon: const Icon(TablerIcons.analyze),
            label: Text(l10n.callAnalyze),
          ),
      ],
    );
  }

  Widget _buildAnalysis(S l10n) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(l10n.callAnalysisResult,
                    style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 8),
                Text('${l10n.voiceTaskTitle}: ${_analysis!['title'] ?? ''}'),
                const SizedBox(height: 4),
                Text('${l10n.voiceDescription}: ${_analysis!['description'] ?? ''}'),
                if (_analysis!['due_date'] != null) ...[
                  const SizedBox(height: 4),
                  Text('${l10n.voiceDueDate}: ${_analysis!['due_date']}'),
                ],
                if (_analysis!['priority'] != null) ...[
                  const SizedBox(height: 4),
                  Text('Priority: ${_analysis!['priority']}'),
                ],
                if (_analysis!['decisions'] != null &&
                    (_analysis!['decisions'] as List).isNotEmpty) ...[
                  const SizedBox(height: 8),
                  ...(_analysis!['decisions'] as List).map(
                    (d) => Padding(
                      padding: const EdgeInsets.only(bottom: 2),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text('- '),
                          Expanded(child: Text(d.toString())),
                        ],
                      ),
                    ),
                  ),
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
                onPressed: _confirming ? null : _reset,
                child: Text(l10n.cancel),
              ),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: FilledButton(
                onPressed: _confirming ? null : _confirmTask,
                child: _confirming
                    ? const SizedBox(
                        height: 20,
                        width: 20,
                        child: CircularProgressIndicator(strokeWidth: 2))
                    : Text(l10n.voiceConfirm),
              ),
            ),
          ],
        ),
      ],
    );
  }

  String _statusText(S l10n) {
    switch (_status) {
      case 'ringing':
        return l10n.callRinging;
      case 'in_progress':
        return l10n.callInProgress;
      case 'analyzing':
        return l10n.callAnalyzing;
      default:
        return l10n.callReady;
    }
  }

  void _reset() {
    setState(() {
      _analysis = null;
      _callId = null;
      _status = 'idle';
      _error = null;
    });
  }

  Future<void> _initiateCall() async {
    final caller = _callerExtCtrl.text.trim();
    final target = _targetExtCtrl.text.trim();
    if (caller.isEmpty || target.isEmpty) return;

    setState(() {
      _status = 'ringing';
      _error = null;
    });

    try {
      final client = ref.read(callRequestClientProvider);
      final result =
          await client.initiateCall(callerExt: caller, targetExt: target);
      _callId = result['call_id'] as String?;
      if (mounted) setState(() => _status = 'in_progress');
    } on DioException catch (e) {
      if (mounted) {
        setState(() {
          _status = 'idle';
          _error = e.response?.data?['detail']?.toString() ??
              e.message ??
              'Connection error';
        });
      }
    }
  }

  Future<void> _analyzeCall() async {
    if (_callId == null) return;
    setState(() {
      _status = 'analyzing';
      _error = null;
    });

    try {
      final client = ref.read(callRequestClientProvider);
      final result = await client.analyzeRecording(_callId!);
      if (mounted) {
        setState(() {
          _analysis = result;
          _status = 'preview';
        });
      }
    } on DioException catch (e) {
      if (mounted) {
        setState(() {
          _status = 'in_progress';
          _error = e.response?.data?['detail']?.toString() ??
              e.message ??
              'Analysis failed';
        });
      }
    }
  }

  Future<void> _confirmTask() async {
    if (_callId == null) return;
    setState(() => _confirming = true);

    try {
      final client = ref.read(callRequestClientProvider);
      final result = await client.confirmCall(_callId!);
      if (mounted) {
        final taskId = result['task_id'];
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Task created (ID: $taskId)')),
        );
        _reset();
      }
    } on DioException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(e.response?.data?['detail']?.toString() ??
                'Failed to create task'),
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _confirming = false);
    }
  }
}
