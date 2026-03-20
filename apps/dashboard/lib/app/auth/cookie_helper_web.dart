// ignore: avoid_web_libraries_in_flutter
import 'dart:html' as html;

/// Read the csrftoken cookie set by InvenTree (Domain=.your-domain.com).
String? readCsrfToken() {
  final cookies = html.document.cookie ?? '';
  for (final part in cookies.split(';')) {
    final trimmed = part.trim();
    if (trimmed.startsWith('csrftoken=')) {
      return trimmed.substring('csrftoken='.length);
    }
  }
  return null;
}
