import 'document.dart';

class SearchResult {
  const SearchResult({
    required this.document,
    this.context,
    this.ranking,
  });

  final OutlineDocument document;
  final String? context;
  final double? ranking;

  factory SearchResult.fromJson(Map<String, dynamic> json) => SearchResult(
        document: OutlineDocument.fromJson(
            json['document'] as Map<String, dynamic>),
        context: json['context'] as String?,
        ranking: (json['ranking'] as num?)?.toDouble(),
      );
}
