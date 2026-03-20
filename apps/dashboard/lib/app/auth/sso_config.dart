class SsoConfig {
  // Authentik OIDC (public client, PKCE)
  static const oidcClientId = String.fromEnvironment(
    'OIDC_CLIENT_ID',
    defaultValue: 'flutter-app-oidc',
  );

  static const oidcIssuer = String.fromEnvironment(
    'OIDC_ISSUER',
    defaultValue: 'https://auth.your-domain.com/application/o/flutter-app/',
  );

  static const oidcAuthorizeUrl =
      'https://auth.your-domain.com/application/o/authorize/';
  static const oidcTokenUrl =
      'https://auth.your-domain.com/application/o/token/';
  static const oidcUserInfoUrl =
      'https://auth.your-domain.com/application/o/userinfo/';
  static const oidcLogoutUrl =
      'https://auth.your-domain.com/application/o/flutter-app/end-session/';

  static const oidcRedirectUri = String.fromEnvironment(
    'OIDC_REDIRECT_URI',
    defaultValue: 'https://app.your-domain.com/auth/callback',
  );

  static const inventreeBaseUrl = String.fromEnvironment(
    'INVENTREE_URL',
    defaultValue: 'https://portal.your-domain.com',
  );

  static const vikunjaBaseUrl = String.fromEnvironment(
    'VIKUNJA_URL',
    defaultValue: 'https://tasks.your-domain.com',
  );

  static const outlineBaseUrl = String.fromEnvironment(
    'OUTLINE_URL',
    defaultValue: 'https://wiki.your-domain.com',
  );

  static const aiAssistantBaseUrl = String.fromEnvironment(
    'AI_ASSISTANT_URL',
    defaultValue: 'https://ai.your-domain.com',
  );
}
