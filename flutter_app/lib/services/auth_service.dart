import 'dart:async';
import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import 'api_client.dart';
import 'google_auth_service.dart';

enum OtpPurpose { login, signup, reset }

String _purposeValue(OtpPurpose purpose) => switch (purpose) {
      OtpPurpose.login => 'login',
      OtpPurpose.signup => 'signup',
      OtpPurpose.reset => 'reset',
    };

OtpPurpose? _purposeFrom(String? value) => switch (value) {
      'login' => OtpPurpose.login,
      'signup' => OtpPurpose.signup,
      'reset' => OtpPurpose.reset,
      _ => null,
    };

class AuthResult {
  final bool ok;
  final String? error;
  final OtpPurpose? purpose;
  final bool otpRequired;
  final bool phoneRequired;
  final String? googleEmail;
  final bool confirmationSent;
  final String? destination;
  final int expiresIn;
  final int resendIn;

  const AuthResult.ok([this.purpose])
      : ok = true,
        error = null,
        otpRequired = false,
        phoneRequired = false,
        googleEmail = null,
        confirmationSent = false,
        destination = null,
        expiresIn = 0,
        resendIn = 0;

  const AuthResult.otp(
    this.purpose, {
    required this.confirmationSent,
    required this.destination,
    required this.expiresIn,
    required this.resendIn,
  })  : ok = true,
        error = null,
        otpRequired = true,
        phoneRequired = false,
        googleEmail = null;

  const AuthResult.googlePhoneRequired(String email)
      : ok = true,
        error = null,
        purpose = null,
        otpRequired = false,
        phoneRequired = true,
        googleEmail = email,
        confirmationSent = false,
        destination = email,
        expiresIn = 0,
        resendIn = 0;

  const AuthResult.fail(this.error)
      : ok = false,
        purpose = null,
        otpRequired = false,
        phoneRequired = false,
        googleEmail = null,
        confirmationSent = false,
        destination = null,
        expiresIn = 0,
        resendIn = 0;
}

class Profile {
  String name, phone, email;
  Profile(this.name, this.phone, this.email);

  String get initials {
    final parts =
        name.trim().split(RegExp(r'\s+')).where((p) => p.isNotEmpty).toList();
    if (parts.isEmpty) {
      return '?';
    }
    if (parts.length == 1) {
      return parts.first.substring(0, 1).toUpperCase();
    }
    return (parts.first.substring(0, 1) + parts.last.substring(0, 1))
        .toUpperCase();
  }
}

class Validators {
  static String? normalizePhone(String raw) {
    var d = raw.replaceAll(RegExp(r'[\s\-\(\)]'), '');
    if (d.startsWith('+')) {
      d = d.substring(1);
    }
    if (d.length == 12 && d.startsWith('256')) {
      d = d.substring(3);
    } else if (d.length == 10 && d.startsWith('0')) {
      d = d.substring(1);
    }
    if (!RegExp(r'^[1-9]\d{8}$').hasMatch(d)) {
      return null;
    }
    return '+256$d';
  }

  static String? phone(String v) {
    if (v.trim().isEmpty) {
      return 'Enter your phone number';
    }
    if (normalizePhone(v) == null) {
      return 'Enter a valid Uganda number, e.g. +256 700 123 456';
    }
    return null;
  }

  static String? name(String v) =>
      v.trim().length < 2 ? 'Enter your full name' : null;

  static String? email(String v) {
    if (v.trim().isEmpty) {
      return 'Enter your email address';
    }
    if (!RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$').hasMatch(v.trim())) {
      return 'Enter a valid email address';
    }
    return null;
  }

  static bool hasLen(String p) => p.length >= 8;
  static bool hasLetterAndNumber(String p) =>
      RegExp(r'[A-Za-z]').hasMatch(p) && RegExp(r'\d').hasMatch(p);
  static bool passwordOk(String p) => hasLen(p) && hasLetterAndNumber(p);
  static String? password(String v) {
    if (v.isEmpty) {
      return 'Create a password';
    }
    if (!passwordOk(v)) {
      return 'Use at least 8 characters with a letter and a number';
    }
    return null;
  }

  /// 0..4 segments for the strength meter.
  static int strength(String p) {
    if (p.isEmpty) {
      return 0;
    }
    var s = 0;
    if (hasLen(p)) {
      s++;
    }
    if (hasLetterAndNumber(p)) {
      s++;
    }
    if (RegExp(r'[a-z]').hasMatch(p) && RegExp(r'[A-Z]').hasMatch(p)) {
      s++;
    }
    if (RegExp(r'[^A-Za-z0-9]').hasMatch(p) || p.length >= 12) {
      s++;
    }
    return s;
  }
}

String formatPhone(String e164) {
  // +256700123456 -> +256 700 123 456
  if (e164.length != 13) {
    return e164;
  }
  return '${e164.substring(0, 4)} ${e164.substring(4, 7)} ${e164.substring(7, 10)} ${e164.substring(10)}';
}

String maskPhone(String e164) {
  if (e164.length != 13) {
    return e164;
  }
  return '${e164.substring(0, 4)} ${e164.substring(4, 7)} ••• ${e164.substring(10)}';
}

String maskEmail(String email) {
  final parts = email.split('@');
  if (parts.length != 2) {
    return email;
  }
  final name = parts.first;
  final visible = name.length <= 2 ? name : '${name.substring(0, 2)}•••';
  return '$visible@${parts.last}';
}

/// Authentication is owned by Django. Only the bearer token and a non-sensitive
/// profile cache live on the device; passwords and account lists never do.
class AuthService {
  static const resendAfter = 30; // seconds
  static const validFor = 120; // seconds
  static const maxAttempts = 5;
  static const _profileKey = 'fc_session_user_v1';

  final ApiClient _api;
  final GoogleAuthService _google;
  final Profile profile = Profile('', '', '');
  Profile? current;

  OtpPurpose? purpose;
  String? pendingPhone;
  String?
      code; // returned only when the backend's development switch is enabled
  String? destination;
  String? deliveryChannel;
  bool confirmationSent = false;
  DateTime? _sentAt;
  DateTime? _expiresAt;

  bool resetVerified = false;
  String? resetPhone;
  String? _resetToken;
  String? _pendingGoogleToken;

  AuthService({ApiClient? api, GoogleAuthService? googleAuth})
      : _api = api ?? ApiClient.instance,
        _google = googleAuth ?? GoogleAuthService();

  bool get isAuthenticated => current != null && _api.hasToken;
  bool get googleConfigured => _google.isConfigured;
  bool get googleUsesWebButton => _google.usesWebButton;
  Stream<String?> get googleIdTokenEvents => _google.idTokenEvents;
  bool get hasPending => purpose != null && pendingPhone != null;

  Future<void> init() async {
    await _api.init();
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_profileKey);
    if (raw != null) {
      try {
        _applyUser(Map<String, dynamic>.from(jsonDecode(raw) as Map));
      } catch (_) {
        await prefs.remove(_profileKey);
      }
    }
    if (!_api.hasToken) {
      await _clearLocal();
      return;
    }
    try {
      final response = await _api.get('/me');
      _applyUser(_userMap(response));
      await _cacheUser();
    } on ApiException catch (error) {
      if (error.status == 401) await _clearLocal();
      // A temporary network failure keeps the cached profile and token intact.
    }
  }

  Map<String, dynamic> _userMap(dynamic response) {
    if (response is! Map || response['user'] is! Map) {
      throw const ApiException(
          'The server returned an invalid account profile.');
    }
    return Map<String, dynamic>.from(response['user'] as Map);
  }

  void _applyUser(Map<String, dynamic> user) {
    final next = Profile(
      (user['name'] ?? '').toString(),
      (user['phone'] ?? '').toString(),
      (user['email'] ?? '').toString(),
    );
    current = next;
    profile
      ..name = next.name
      ..phone = next.phone
      ..email = next.email;
  }

  Future<void> _cacheUser() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
        _profileKey,
        jsonEncode({
          'name': profile.name,
          'phone': profile.phone,
          'email': profile.email,
        }));
  }

  Future<void> _saveSession(String token, Map<String, dynamic> user) async {
    await _api.saveToken(token);
    _applyUser(user);
    await _cacheUser();
  }

  AuthResult _failure(Object error) {
    if (error is ApiException) {
      return AuthResult.fail(error.message);
    }
    if (error is GoogleAuthException) {
      return AuthResult.fail(error.message);
    }
    return const AuthResult.fail(
        'We couldn’t reach FuelOnDemand. Check your connection and try again.');
  }

  void _applyChallenge(dynamic response, OtpPurpose fallback) {
    if (response is! Map) {
      throw const ApiException(
          'The server returned an invalid verification response.');
    }
    purpose = _purposeFrom(response['purpose']?.toString()) ?? fallback;
    pendingPhone =
        Validators.normalizePhone(response['phone']?.toString() ?? '') ??
            response['phone']?.toString();
    code = response['dev_code']?.toString();
    final delivery = response['delivery'];
    deliveryChannel = delivery is Map ? delivery['channel']?.toString() : null;
    destination = response['destination']?.toString() ??
        (delivery is Map ? delivery['destination']?.toString() : null);
    confirmationSent = response['confirmation_sent'] == true;
    _sentAt = DateTime.now();
    final seconds =
        int.tryParse(response['expires_in']?.toString() ?? '') ?? validFor;
    _expiresAt = _sentAt!.add(Duration(seconds: seconds));
    resetVerified = false;
    resetPhone = null;
    _resetToken = null;
  }

  AuthResult _challengeResult(dynamic response, OtpPurpose fallback) {
    _applyChallenge(response, fallback);
    return AuthResult.otp(
      purpose!,
      confirmationSent: confirmationSent,
      destination: destination,
      expiresIn: _expiresAt!.difference(_sentAt!).inSeconds,
      resendIn:
          int.tryParse((response as Map)['resend_in']?.toString() ?? '') ??
              resendAfter,
    );
  }

  Future<AuthResult> _sessionOrChallenge(
      dynamic response, OtpPurpose fallback) async {
    if (response is Map && response['token'] is String) {
      await _saveSession(response['token'] as String, _userMap(response));
      return const AuthResult.ok();
    }
    return _challengeResult(response, fallback);
  }

  // ----- sign in / up ------------------------------------------------------
  Future<AuthResult> signIn(String phone, String password) async {
    final normalized = Validators.normalizePhone(phone);
    if (normalized == null) {
      return const AuthResult.fail('Enter a valid Uganda phone number.');
    }
    try {
      final response = await _api.post('/auth/login',
          body: {'phone': normalized, 'password': password});
      return await _sessionOrChallenge(response, OtpPurpose.login);
    } catch (error) {
      return _failure(error);
    }
  }

  Future<AuthResult> signUp({
    required String name,
    required String phone,
    required String email,
    required String password,
  }) async {
    final normalized = Validators.normalizePhone(phone);
    if (normalized == null) {
      return const AuthResult.fail('Enter a valid Uganda phone number.');
    }
    try {
      final response = await _api.post('/auth/register', body: {
        'name': name.trim(),
        'phone': normalized,
        'email': email.trim(),
        'password': password,
      });
      return await _sessionOrChallenge(response, OtpPurpose.signup);
    } catch (error) {
      return _failure(error);
    }
  }

  Future<AuthResult> signInWithGoogle({String? phone, String? idToken}) async {
    if (!_google.isConfigured) {
      return const AuthResult.fail(
          'Google sign-in is not configured. Add GOOGLE_SERVER_CLIENT_ID for Android or GOOGLE_CLIENT_ID for web/iOS to the app build.');
    }
    if (phone != null && Validators.normalizePhone(phone) == null) {
      return const AuthResult.fail('Enter a valid Uganda phone number.');
    }
    try {
      final token = idToken ?? _pendingGoogleToken ?? await _google.idToken();
      if (token == null || token.isEmpty) {
        return const AuthResult.fail('Google sign-in was cancelled.');
      }
      _pendingGoogleToken = token;
      final normalized =
          phone == null ? null : Validators.normalizePhone(phone);
      final response = await _api.post('/auth/google', body: {
        'id_token': token,
        if (normalized != null) 'phone': normalized,
      });
      if (response is Map && response['phone_required'] == true) {
        return AuthResult.googlePhoneRequired(
            response['email']?.toString() ?? '');
      }
      if (response is Map && response['token'] is String) {
        await _saveSession(response['token'] as String, _userMap(response));
        _pendingGoogleToken = null;
        return const AuthResult.ok();
      }
      _pendingGoogleToken = null;
      return const AuthResult.fail(
          'Google sign-in could not be completed. Please try again.');
    } catch (error) {
      _pendingGoogleToken = null;
      return _failure(error);
    }
  }

  Future<void> cancelGoogleSignIn() async {
    _pendingGoogleToken = null;
    try {
      await _google.signOut();
    } catch (_) {
      // Cancelling phone completion must still dismiss the sheet.
    }
  }

  Future<AuthResult> requestPasswordReset(String phone) async {
    final normalized = Validators.normalizePhone(phone);
    if (normalized == null) {
      return const AuthResult.fail('Enter a valid Uganda phone number.');
    }
    try {
      final response =
          await _api.post('/auth/forgot', body: {'phone': normalized});
      return _challengeResult(response, OtpPurpose.reset);
    } catch (error) {
      return _failure(error);
    }
  }

  // ----- verification code -------------------------------------------------
  int get secondsLeft {
    if (_expiresAt == null) {
      return 0;
    }
    final seconds = _expiresAt!.difference(DateTime.now()).inSeconds;
    return seconds > 0 ? seconds : 0;
  }

  int get resendIn {
    if (_sentAt == null) {
      return 0;
    }
    final seconds = resendAfter - DateTime.now().difference(_sentAt!).inSeconds;
    return seconds > 0 ? seconds : 0;
  }

  Future<AuthResult> startOtp(OtpPurpose requested,
      {required String phone}) async {
    final normalized = Validators.normalizePhone(phone);
    if (normalized == null) {
      return const AuthResult.fail('Enter a valid Uganda phone number.');
    }
    try {
      final response = await _api.post('/auth/otp/send', body: {
        'phone': normalized,
        'purpose': _purposeValue(requested),
      });
      return _challengeResult(response, requested);
    } catch (error) {
      return _failure(error);
    }
  }

  Future<AuthResult> verifyOtp(String entered) async {
    if (!hasPending) {
      return const AuthResult.fail('Request a new code to continue.');
    }
    final requested = purpose!;
    final phone = pendingPhone!;
    try {
      final response = await _api.post('/auth/otp/verify', body: {
        'phone': phone,
        'purpose': _purposeValue(requested),
        'code': entered.trim(),
      });
      if (requested == OtpPurpose.reset) {
        _resetToken = (response as Map)['reset_token']?.toString();
        resetVerified = _resetToken != null;
        resetPhone = phone;
        _clearPending();
        return resetVerified
            ? AuthResult.ok(requested)
            : const AuthResult.fail('The server did not return a reset token.');
      }
      final result = await _sessionOrChallenge(response, requested);
      if (!result.ok || result.otpRequired) {
        return result;
      }
      _clearPending();
      return AuthResult.ok(requested);
    } catch (error) {
      return _failure(error);
    }
  }

  void _clearPending() {
    purpose = null;
    pendingPhone = null;
    code = null;
    destination = null;
    deliveryChannel = null;
    confirmationSent = false;
    _sentAt = null;
    _expiresAt = null;
  }

  // ----- password reset ----------------------------------------------------
  Future<AuthResult> resetPassword(String newPassword) async {
    if (!resetVerified || resetPhone == null || _resetToken == null) {
      return const AuthResult.fail(
          'Please verify your account before changing the password.');
    }
    try {
      await _api.post('/auth/reset', body: {
        'phone': resetPhone,
        'reset_token': _resetToken,
        'password': newPassword,
        'password_confirmation': newPassword,
      });
      resetVerified = false;
      resetPhone = null;
      _resetToken = null;
      return const AuthResult.ok();
    } catch (error) {
      return _failure(error);
    }
  }

  // ----- profile / session -------------------------------------------------
  Future<AuthResult> updateProfile(String name, String email) async {
    if (!isAuthenticated) {
      return const AuthResult.fail('Please sign in to update your profile.');
    }
    try {
      final response = await _api
          .put('/me', body: {'name': name.trim(), 'email': email.trim()});
      _applyUser(_userMap(response));
      await _cacheUser();
      return const AuthResult.ok();
    } catch (error) {
      return _failure(error);
    }
  }

  Future<void> signOut() async {
    try {
      if (_api.hasToken) {
        await _api.post('/auth/logout');
      }
    } catch (_) {
      // Local sign-out must still succeed when the network is unavailable.
    }
    try {
      await _google.signOut();
    } catch (_) {
      // Google sign-out is best-effort; local sign-out must always succeed.
    }
    await _api.clearToken();
    await _clearLocal();
  }

  void handleUnauthorized() {
    unawaited(_clearLocal());
  }

  Future<void> _clearLocal() async {
    current = null;
    profile
      ..name = ''
      ..phone = ''
      ..email = '';
    _clearPending();
    resetVerified = false;
    resetPhone = null;
    _resetToken = null;
    _pendingGoogleToken = null;
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_profileKey);
  }
}

final auth = AuthService();
