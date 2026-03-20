import 'package:flutter_test/flutter_test.dart';
import 'package:shinbee_dashboard/vikunja/api/endpoints.dart';
import 'package:shinbee_dashboard/vikunja/models/project.dart';
import 'package:shinbee_dashboard/vikunja/models/task.dart';

void main() {
  group('Vikunja endpoints', () {
    test('project tasks URL is correct', () {
      expect(VikunjaEndpoints.projectTasks(1), '/api/v1/projects/1/tasks');
    });

    test('project buckets URL is correct', () {
      expect(VikunjaEndpoints.projectBuckets(5), '/api/v1/projects/5/buckets');
    });
  });

  group('Vikunja models', () {
    test('Project fromJson', () {
      final json = {
        'id': 1,
        'title': 'Test Project',
        'description': 'A test project',
        'is_archived': false,
        'hex_color': 'ff0000',
      };
      final project = Project.fromJson(json);
      expect(project.id, 1);
      expect(project.title, 'Test Project');
      expect(project.hexColor, 'ff0000');
    });

    test('VikunjaTask fromJson', () {
      final json = {
        'id': 10,
        'title': 'Fix bug',
        'done': false,
        'priority': 2,
        'project_id': 1,
        'labels': [
          {'id': 1, 'title': 'bug', 'hex_color': 'ff0000'},
        ],
      };
      final task = VikunjaTask.fromJson(json);
      expect(task.id, 10);
      expect(task.title, 'Fix bug');
      expect(task.priority, 2);
      expect(task.labels, isNotEmpty);
      expect(task.labels!.first.title, 'bug');
    });
  });
}
