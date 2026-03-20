/// Compile-time test mode configuration.
///
/// Build with: flutter build web --dart-define=TEST_MODE=true
/// Optionally override URLs:
///   --dart-define=TEST_INVENTREE_URL=https://test-portal.your-domain.com
class TestAuthConfig {
  static const bool isTestMode = bool.fromEnvironment(
    'TEST_MODE',
    defaultValue: false,
  );

  static const String testInventreeUrl = String.fromEnvironment(
    'TEST_INVENTREE_URL',
    defaultValue: 'https://test-portal.your-domain.com',
  );

  static const String testApiUrl = String.fromEnvironment(
    'TEST_API_URL',
    defaultValue: 'https://test-api.your-domain.com',
  );
}
