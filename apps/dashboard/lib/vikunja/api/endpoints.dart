class VikunjaEndpoints {
  static const base = '/api/v1';
  static const projects = '$base/projects';
  static const tasks = '$base/tasks';
  static const labels = '$base/labels';
  static const users = '$base/users';

  static String projectTasks(int projectId) => '$projects/$projectId/tasks';
  static String projectBuckets(int projectId) => '$projects/$projectId/buckets';
  static String task(int taskId) => '$tasks/$taskId';
}
