import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fuelconnect/core/core.dart';
import 'package:fuelconnect/screens/auth_screens.dart';
import 'package:fuelconnect/services/api_client.dart';
import 'package:fuelconnect/services/auth_service.dart';
import 'package:fuelconnect/services/google_auth_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

class FakeApiClient implements ApiClient {
  final List<Map<String, dynamic>> posts = [];
  final List<dynamic> queuedResponses = [];
  Map<String, dynamic> response = {};
  Map<String, dynamic>? getResponse;
  Object? error;
  String? token;

  @override
  bool get hasToken => token != null;

  @override
  Future<void> init() async {}

  @override
  Future<void> saveToken(String value) async => token = value;

  @override
  Future<void> clearToken() async => token = null;

  @override
  Future<dynamic> post(String path, {Object? body}) async {
    posts.add({'path': path, 'body': body});
    if (queuedResponses.isNotEmpty) {
      final next = queuedResponses.removeAt(0);
      if (next is Exception) throw next;
      return next;
    }
    if (error != null) throw error!;
    return response;
  }

  @override
  Future<dynamic> get(String path, {Map<String, String>? query}) async =>
      getResponse ?? response;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class FakeGoogleAuthService implements GoogleAuthService {
  @override
  final bool isConfigured;
  @override
  final bool usesWebButton = false;

  final String? token;
  final Object? error;
  int tokenRequests = 0;
  int signOuts = 0;

  FakeGoogleAuthService({
    this.token = 'google-id-token',
    this.isConfigured = true,
    this.error,
  });

  @override
  Stream<String?> get idTokenEvents => const Stream<String?>.empty();

  @override
  Future<String?> idToken() async {
    tokenRequests++;
    if (error != null) throw error!;
    return token;
  }

  @override
  Future<void> signOut() async => signOuts++;
}

Map<String, dynamic> googleSession() => {
      'token': 'server-token',
      'user': {
        'name': 'Google Customer',
        'phone': '+256700123456',
        'email': 'google.customer@example.com',
        'is_verified': true,
      },
    };

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  group('phone validation', () {
    test('normalises Uganda numbers', () {
      expect(Validators.normalizePhone('0700123456'), '+256700123456');
      expect(Validators.normalizePhone('+256 700 123 456'), '+256700123456');
      expect(Validators.normalizePhone('700123456'), '+256700123456');
    });
    test('rejects bad numbers', () {
      expect(Validators.normalizePhone('12345'), isNull);
      expect(Validators.phone(''), isNotNull);
    });
  });

  group('password rules', () {
    test('needs 8+ chars with a letter and a number', () {
      expect(Validators.passwordOk('short1'), isFalse);
      expect(Validators.passwordOk('longpassword'), isFalse);
      expect(Validators.passwordOk('Fuel@2025'), isTrue);
    });
    test('strength meter grows with variety', () {
      expect(Validators.strength(''), 0);
      expect(Validators.strength('Fuel@2025xyz'), 4);
    });
  });

  group('OTP navigation', () {
    testWidgets(
        'keeps an active challenge when state changes before the first frame',
        (tester) async {
      app.go(Screen.otp, root: true);
      auth
        ..purpose = OtpPurpose.signup
        ..pendingPhone = '+256700123456'
        ..destination = 'customer@example.com'
        ..confirmationSent = true;

      // Simulate verification clearing the challenge between initState and the
      // screen's deferred entry check.
      WidgetsBinding.instance.addPostFrameCallback((_) {
        auth
          ..purpose = null
          ..pendingPhone = null;
      });

      await tester
          .pumpWidget(MaterialApp(home: Scaffold(body: OtpScreen(go: app.go))));
      await tester.pump();

      expect(app.current, Screen.otp);
      auth
        ..destination = null
        ..confirmationSent = false;
      app.go(Screen.login, root: true);
      await tester.pumpWidget(const SizedBox.shrink());
    });
  });

  group('backend authentication', () {
    test('registration uses the API and keeps the confirmation challenge',
        () async {
      final api = FakeApiClient()
        ..response = {
          'otp_required': true,
          'phone': '+256700123456',
          'purpose': 'signup',
          'dev_code': '123456',
          'confirmation_sent': true,
          'destination': 'customer@example.com',
          'delivery': {'channel': 'email'},
          'expires_in': 120,
          'resend_in': 30,
        };
      final service = AuthService(api: api);

      final result = await service.signUp(
        name: 'Test Customer',
        phone: '0700123456',
        email: 'customer@example.com',
        password: 'Fuel@2026',
      );

      expect(result.ok, isTrue);
      expect(result.otpRequired, isTrue);
      expect(result.purpose, OtpPurpose.signup);
      expect(service.hasPending, isTrue);
      expect(service.code, '123456');
      expect(service.destination, 'customer@example.com');
      expect(api.posts.single['path'], '/auth/register');
      expect(api.posts.single['body'], containsPair('phone', '+256700123456'));
    });

    test('sign-up verification stores the bearer token and server profile',
        () async {
      final api = FakeApiClient()
        ..response = {
          'otp_required': true,
          'phone': '+256700123456',
          'purpose': 'signup',
          'dev_code': '123456',
          'confirmation_sent': true,
          'expires_in': 120,
          'resend_in': 30,
        };
      final service = AuthService(api: api);
      await service.signUp(
        name: 'Test Customer',
        phone: '+256700123456',
        email: 'customer@example.com',
        password: 'Fuel@2026',
      );
      api.response = {
        'token': 'server-token',
        'user': {
          'name': 'Test Customer',
          'phone': '+256700123456',
          'email': 'customer@example.com',
          'is_verified': true,
        },
      };

      final result = await service.verifyOtp('123456');

      expect(result.ok, isTrue);
      expect(result.purpose, OtpPurpose.signup);
      expect(service.isAuthenticated, isTrue);
      expect(service.profile.name, 'Test Customer');
      expect(service.profile.email, 'customer@example.com');
      expect(api.token, 'server-token');
      expect(service.hasPending, isFalse);
      expect(api.posts.last['path'], '/auth/otp/verify');
    });

    test('password-only login goes straight into an authenticated session',
        () async {
      final api = FakeApiClient()
        ..response = {
          'token': 'server-token',
          'user': {
            'name': 'Returning Customer',
            'phone': '+256700123456',
            'email': 'returning@example.com',
          },
        };
      final service = AuthService(api: api);

      final result = await service.signIn('+256700123456', 'Fuel@2026');

      expect(result.ok, isTrue);
      expect(result.otpRequired, isFalse);
      expect(service.isAuthenticated, isTrue);
      expect(service.profile.name, 'Returning Customer');
    });

    test('API errors are shown without creating a local account', () async {
      final api = FakeApiClient()
        ..error = const ApiException(
            'That phone number or password is not correct.', 401);
      final service = AuthService(api: api);

      final result = await service.signIn('+256700123456', 'Wrong@2026');

      expect(result.ok, isFalse);
      expect(result.error, contains('not correct'));
      expect(service.isAuthenticated, isFalse);
    });

    test('Google sign-in exchanges the ID token and stores the session',
        () async {
      final api = FakeApiClient()..response = googleSession();
      final google = FakeGoogleAuthService();
      final service = AuthService(api: api, googleAuth: google);

      final result = await service.signInWithGoogle();

      expect(result.ok, isTrue);
      expect(google.tokenRequests, 1);
      expect(api.posts.single['path'], '/auth/google');
      expect(api.posts.single['body'],
          containsPair('id_token', 'google-id-token'));
      expect(api.token, 'server-token');
      expect(service.isAuthenticated, isTrue);
      expect(service.profile.email, 'google.customer@example.com');
      final prefs = await SharedPreferences.getInstance();
      expect(prefs.getString('fc_session_user_v1'),
          contains('google.customer@example.com'));
    });

    test('Google phone completion reuses the token and normalises the number',
        () async {
      final api = FakeApiClient()
        ..queuedResponses.addAll([
          {
            'phone_required': true,
            'email': 'google.customer@example.com',
            'name': 'Google Customer',
          },
          googleSession(),
        ]);
      final google = FakeGoogleAuthService();
      final service = AuthService(api: api, googleAuth: google);

      final challenge = await service.signInWithGoogle();
      expect(challenge.ok, isTrue);
      expect(challenge.phoneRequired, isTrue);
      expect(challenge.googleEmail, 'google.customer@example.com');
      expect(service.isAuthenticated, isFalse);

      final result = await service.signInWithGoogle(phone: '0700123456');

      expect(result.ok, isTrue);
      expect(google.tokenRequests, 1);
      expect(api.posts, hasLength(2));
      expect(
          api.posts.first['body'], containsPair('id_token', 'google-id-token'));
      expect(api.posts.last['body'], containsPair('phone', '+256700123456'));
      expect(service.isAuthenticated, isTrue);
    });

    test('the official web button can hand its ID token to the same flow',
        () async {
      final api = FakeApiClient()..response = googleSession();
      final google = FakeGoogleAuthService();
      final service = AuthService(api: api, googleAuth: google);

      final result = await service.signInWithGoogle(idToken: 'web-id-token');

      expect(result.ok, isTrue);
      expect(google.tokenRequests, 0);
      expect(
          api.posts.single['body'], containsPair('id_token', 'web-id-token'));
    });

    test('missing Google configuration does not call Google or the API',
        () async {
      final api = FakeApiClient();
      final google = FakeGoogleAuthService(isConfigured: false);
      final service = AuthService(api: api, googleAuth: google);

      final result = await service.signInWithGoogle();

      expect(result.ok, isFalse);
      expect(result.error, contains('not configured'));
      expect(google.tokenRequests, 0);
      expect(api.posts, isEmpty);
    });

    test('Google errors are shown to the user', () async {
      final api = FakeApiClient();
      final google = FakeGoogleAuthService(
        error: const GoogleAuthException(
            'Google sign-in failed. Please try again.'),
      );
      final service = AuthService(api: api, googleAuth: google);

      final result = await service.signInWithGoogle();

      expect(result.ok, isFalse);
      expect(result.error, 'Google sign-in failed. Please try again.');
      expect(api.posts, isEmpty);
    });

    test('cancelled Google sign-in does not create a session', () async {
      final api = FakeApiClient();
      final google = FakeGoogleAuthService(token: null);
      final service = AuthService(api: api, googleAuth: google);

      final result = await service.signInWithGoogle();

      expect(result.ok, isFalse);
      expect(result.error, contains('cancelled'));
      expect(api.posts, isEmpty);
      expect(service.isAuthenticated, isFalse);
    });

    test('a saved Google session is restored on app restart', () async {
      final api = FakeApiClient()..response = googleSession();
      final google = FakeGoogleAuthService();
      final service = AuthService(api: api, googleAuth: google);
      await service.signInWithGoogle();
      api.getResponse = {'user': googleSession()['user']};
      final restored = AuthService(api: api, googleAuth: google);

      await restored.init();

      expect(restored.isAuthenticated, isTrue);
      expect(restored.profile.email, 'google.customer@example.com');
      expect(restored.profile.phone, '+256700123456');
    });

    test('sign-out calls the API and clears the saved session', () async {
      final api = FakeApiClient()..token = 'server-token';
      final google = FakeGoogleAuthService();
      final service = AuthService(api: api, googleAuth: google);
      api.response = {
        'token': 'server-token',
        'user': {
          'name': 'Test Customer',
          'phone': '+256700123456',
          'email': 'customer@example.com'
        },
      };
      await service.signIn('+256700123456', 'Fuel@2026');

      await service.signOut();

      expect(api.posts.last['path'], '/auth/logout');
      expect(google.signOuts, 1);
      expect(api.token, isNull);
      expect(service.isAuthenticated, isFalse);
      expect(service.profile.name, isEmpty);
    });
  });
}
