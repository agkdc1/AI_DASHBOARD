import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shinbee_dashboard/shared/l10n/generated/app_localizations.dart';
import 'package:go_router/go_router.dart';
import 'package:table_calendar/table_calendar.dart';

import '../models/task.dart';
import '../providers/tasks_provider.dart';

class CalendarScreen extends ConsumerStatefulWidget {
  const CalendarScreen({required this.projectId, super.key});

  final String projectId;

  @override
  ConsumerState<CalendarScreen> createState() => _CalendarScreenState();
}

class _CalendarScreenState extends ConsumerState<CalendarScreen> {
  CalendarFormat _calendarFormat = CalendarFormat.month;
  DateTime _focusedDay = DateTime.now();
  DateTime? _selectedDay;

  @override
  Widget build(BuildContext context) {
    final l10n = S.of(context);
    final id = int.tryParse(widget.projectId);
    if (id == null) {
      return Scaffold(
        appBar: AppBar(title: Text(l10n.calendar)),
        body: const Center(child: Text('Invalid project ID')),
      );
    }

    final tasksAsync = ref.watch(projectTasksProvider(id));

    return Scaffold(
      appBar: AppBar(title: Text(l10n.calendar)),
      body: tasksAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('${l10n.error}: $e')),
        data: (tasks) {
          final eventMap = _buildEventMap(tasks);
          final selectedTasks = _selectedDay != null
              ? eventMap[DateTime(
                      _selectedDay!.year, _selectedDay!.month, _selectedDay!.day)] ??
                  []
              : <VikunjaTask>[];

          return Column(
            children: [
              TableCalendar<VikunjaTask>(
                firstDay: DateTime(2020),
                lastDay: DateTime(2030),
                focusedDay: _focusedDay,
                calendarFormat: _calendarFormat,
                selectedDayPredicate: (day) => isSameDay(_selectedDay, day),
                eventLoader: (day) =>
                    eventMap[DateTime(day.year, day.month, day.day)] ?? [],
                onDaySelected: (selected, focused) {
                  setState(() {
                    _selectedDay = selected;
                    _focusedDay = focused;
                  });
                },
                onFormatChanged: (format) {
                  setState(() => _calendarFormat = format);
                },
                onPageChanged: (focused) => _focusedDay = focused,
              ),
              const Divider(),
              Expanded(
                child: ListView.builder(
                  itemCount: selectedTasks.length,
                  itemBuilder: (context, index) {
                    final task = selectedTasks[index];
                    return ListTile(
                      title: Text(task.title),
                      leading: Icon(
                        task.done
                            ? Icons.check_circle
                            : Icons.circle_outlined,
                      ),
                      onTap: () => context.go('/tasks/task/${task.id}'),
                    );
                  },
                ),
              ),
            ],
          );
        },
      ),
    );
  }

  Map<DateTime, List<VikunjaTask>> _buildEventMap(List<VikunjaTask> tasks) {
    final map = <DateTime, List<VikunjaTask>>{};
    for (final task in tasks) {
      if (task.dueDate != null && task.dueDate!.isNotEmpty) {
        try {
          final date = DateTime.parse(task.dueDate!);
          final key = DateTime(date.year, date.month, date.day);
          map.putIfAbsent(key, () => []).add(task);
        } catch (_) {}
      }
    }
    return map;
  }
}
