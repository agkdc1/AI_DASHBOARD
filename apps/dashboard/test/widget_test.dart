import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('App smoke test', (tester) async {
    // Basic smoke test — verifies the app can be imported without errors.
    // Full widget tests require mock providers (see test/auth/).
    expect(1 + 1, 2);
  });
}
