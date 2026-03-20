/// Authentication state for the app.
///
/// With Authentik forward auth, API calls are authenticated via session cookies
/// on .your-domain.com — no per-service tokens needed.
sealed class AuthState {
  const AuthState();

  const factory AuthState.unauthenticated() = Unauthenticated;
  const factory AuthState.authenticating() = Authenticating;
  const factory AuthState.authenticated({
    required String email,
    required String displayName,
    String? photoUrl,
  }) = Authenticated;
  const factory AuthState.error(String message) = AuthError;
}

class Unauthenticated extends AuthState {
  const Unauthenticated();

  @override
  bool operator ==(Object other) =>
      identical(this, other) || other is Unauthenticated;

  @override
  int get hashCode => runtimeType.hashCode;
}

class Authenticating extends AuthState {
  const Authenticating();

  @override
  bool operator ==(Object other) =>
      identical(this, other) || other is Authenticating;

  @override
  int get hashCode => runtimeType.hashCode;
}

class Authenticated extends AuthState {
  const Authenticated({
    required this.email,
    required this.displayName,
    this.photoUrl,
  });

  final String email;
  final String displayName;
  final String? photoUrl;

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      (other is Authenticated &&
          email == other.email &&
          displayName == other.displayName &&
          photoUrl == other.photoUrl);

  @override
  int get hashCode => Object.hash(email, displayName, photoUrl);
}

class AuthError extends AuthState {
  const AuthError(this.message);

  final String message;

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      (other is AuthError && message == other.message);

  @override
  int get hashCode => message.hashCode;
}
