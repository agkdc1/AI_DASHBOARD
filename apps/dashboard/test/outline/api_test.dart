import 'package:flutter_test/flutter_test.dart';
import 'package:shinbee_dashboard/outline/api/endpoints.dart';
import 'package:shinbee_dashboard/outline/models/document.dart';
import 'package:shinbee_dashboard/outline/models/collection.dart';

void main() {
  group('Outline endpoints', () {
    test('endpoints use POST convention', () {
      expect(OutlineEndpoints.documentsList, '/api/documents.list');
      expect(OutlineEndpoints.documentsSearch, '/api/documents.search');
      expect(OutlineEndpoints.collectionsList, '/api/collections.list');
    });
  });

  group('Outline models', () {
    test('OutlineDocument fromJson', () {
      final json = {
        'id': 'doc-uuid-001',
        'title': 'Getting Started',
        'text': '# Welcome\nThis is a test document.',
        'emoji': '📖',
        'collectionId': 'col-uuid-001',
        'archived': false,
        'template': false,
        'createdAt': '2026-01-01T00:00:00Z',
        'updatedAt': '2026-02-01T00:00:00Z',
      };
      final doc = OutlineDocument.fromJson(json);
      expect(doc.id, 'doc-uuid-001');
      expect(doc.title, 'Getting Started');
      expect(doc.text, contains('Welcome'));
      expect(doc.emoji, '📖');
    });

    test('OutlineCollection fromJson', () {
      final json = {
        'id': 'col-uuid-001',
        'name': 'Engineering',
        'description': 'Engineering docs',
        'permission': 'read_write',
      };
      final col = OutlineCollection.fromJson(json);
      expect(col.id, 'col-uuid-001');
      expect(col.name, 'Engineering');
    });
  });
}
