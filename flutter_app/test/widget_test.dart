import 'package:flutter_test/flutter_test.dart';
import 'package:fuelconnect/services/api_client.dart';
import 'package:fuelconnect/services/auth_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

class FakeApiClient implements ApiClient {
  final List<Map<String, dynamic>> posts = [];
  Map<String, dynamic> response = {};
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
    if (error != null) throw error!;
    return response;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

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

    test('sign-out calls the API and clears the saved session', () async {
      final api = FakeApiClient()..token = 'server-token';
      final service = AuthService(api: api);
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
      expect(api.token, isNull);
      expect(service.isAuthenticated, isFalse);
      expect(service.profile.name, isEmpty);
    });
  });
}
