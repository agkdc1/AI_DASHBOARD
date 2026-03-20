import 'package:flutter/material.dart';
import 'package:shinbee_dashboard/shared/l10n/generated/app_localizations.dart';

class TaskForm extends StatefulWidget {
  const TaskForm({
    this.initialTitle = '',
    this.initialDescription = '',
    this.initialPriority = 0,
    this.initialDueDate,
    required this.onSave,
    super.key,
  });

  final String initialTitle;
  final String initialDescription;
  final int initialPriority;
  final DateTime? initialDueDate;
  final void Function(String title, String description, int priority, DateTime? dueDate) onSave;

  @override
  State<TaskForm> createState() => _TaskFormState();
}

class _TaskFormState extends State<TaskForm> {
  late final _titleController = TextEditingController(text: widget.initialTitle);
  late final _descController = TextEditingController(text: widget.initialDescription);
  late int _priority = widget.initialPriority;
  DateTime? _dueDate;

  @override
  void initState() {
    super.initState();
    _dueDate = widget.initialDueDate;
  }

  @override
  void dispose() {
    _titleController.dispose();
    _descController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = S.of(context);
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        TextField(
          controller: _titleController,
          decoration: const InputDecoration(labelText: 'Title'),
          autofocus: true,
        ),
        const SizedBox(height: 8),
        TextField(
          controller: _descController,
          decoration: const InputDecoration(labelText: 'Description'),
          maxLines: 3,
        ),
        const SizedBox(height: 8),
        DropdownButtonFormField<int>(
          value: _priority,
          decoration: const InputDecoration(labelText: 'Priority'),
          items: const [
            DropdownMenuItem(value: 0, child: Text('None')),
            DropdownMenuItem(value: 1, child: Text('Low')),
            DropdownMenuItem(value: 2, child: Text('Medium')),
            DropdownMenuItem(value: 3, child: Text('High')),
          ],
          onChanged: (v) => setState(() => _priority = v ?? 0),
        ),
        const SizedBox(height: 8),
        ListTile(
          contentPadding: EdgeInsets.zero,
          title: Text(_dueDate != null
              ? 'Due: ${_dueDate!.toIso8601String().substring(0, 10)}'
              : 'No due date'),
          trailing: IconButton(
            icon: const Icon(Icons.calendar_today),
            onPressed: () async {
              final picked = await showDatePicker(
                context: context,
                initialDate: _dueDate ?? DateTime.now(),
                firstDate: DateTime(2020),
                lastDate: DateTime(2030),
              );
              if (picked != null) setState(() => _dueDate = picked);
            },
          ),
        ),
        const SizedBox(height: 16),
        Row(
          mainAxisAlignment: MainAxisAlignment.end,
          children: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: Text(l10n.cancel),
            ),
            const SizedBox(width: 8),
            FilledButton(
              onPressed: () {
                widget.onSave(
                  _titleController.text,
                  _descController.text,
                  _priority,
                  _dueDate,
                );
                Navigator.of(context).pop();
              },
              child: Text(l10n.save),
            ),
          ],
        ),
      ],
    );
  }
}
