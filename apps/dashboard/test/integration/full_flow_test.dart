import 'package:flutter_test/flutter_test.dart';
import 'package:shinbee_dashboard/app/auth/auth_state.dart';

/// Integration test skeleton — requires mock backends to be running.
/// Run with: flutter test --dart-define=MOCK_OIDC_URL=http://localhost:8080
void main() {
  group('Full auth flow', () {
    test('unauthenticated -> authenticating -> authenticated', () {
      // Step 1: Start unauthenticated
      const state1 = AuthState.unauthenticated();
      expect(state1, isA<Unauthenticated>());

      // Step 2: Transition to authenticating
      const state2 = AuthState.authenticating();
      expect(state2, isA<Authenticating>());

      // Step 3: Arrive at authenticated with all 3 tokens
      const state3 = AuthState.authenticated(
        inventreeToken: 'inv-test-token',
        vikunjaToken: 'vik-test-token',
        outlineToken: 'out-test-token',
        email: 'test@your-domain.com',
        displayName: 'Test User',
      );
      expect(state3, isA<Authenticated>());
      final auth = state3 as Authenticated;
      expect(auth.inventreeToken, isNotEmpty);
      expect(auth.vikunjaToken, isNotEmpty);
      expect(auth.outlineToken, isNotEmpty);
    });

    test('error state holds message', () {
      const state = AuthState.error('Token exchange failed');
      expect(state, isA<AuthError>());
      expect((state as AuthError).message, contains('Token exchange'));
    });
  });
}
