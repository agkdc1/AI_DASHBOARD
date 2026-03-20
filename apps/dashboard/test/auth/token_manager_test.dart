import 'package:flutter_test/flutter_test.dart';
import 'package:shinbee_dashboard/app/auth/auth_state.dart';

void main() {
  group('AuthState', () {
    test('unauthenticated is default', () {
      const state = AuthState.unauthenticated();
      expect(state, isA<Unauthenticated>());
    });

    test('authenticated holds tokens', () {
      const state = AuthState.authenticated(
        inventreeToken: 'inv-token',
        vikunjaToken: 'vik-token',
        outlineToken: 'out-token',
        email: 'test@your-domain.com',
        displayName: 'Test User',
      );
      expect(state, isA<Authenticated>());
      final auth = state as Authenticated;
      expect(auth.inventreeToken, 'inv-token');
      expect(auth.vikunjaToken, 'vik-token');
      expect(auth.outlineToken, 'out-token');
      expect(auth.email, 'test@your-domain.com');
    });

    test('error holds message', () {
      const state = AuthState.error('Something went wrong');
      expect(state, isA<AuthError>());
      expect((state as AuthError).message, 'Something went wrong');
    });
  });
}
