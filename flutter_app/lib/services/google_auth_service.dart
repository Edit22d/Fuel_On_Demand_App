import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:google_sign_in/google_sign_in.dart';

class GoogleAuthException implements Exception {
  final String message;

  const GoogleAuthException(this.message);

  @override
  String toString() => message;
}

class GoogleAuthConfig {
  static const clientId = String.fromEnvironment('GOOGLE_CLIENT_ID');
  static const serverClientId =
      String.fromEnvironment('GOOGLE_SERVER_CLIENT_ID');
}

class GoogleAuthService {
  final GoogleSignIn? _googleSignIn;

  GoogleAuthService({GoogleSignIn? googleSignIn})
      : _googleSignIn = googleSignIn ?? _configuredGoogleSignIn();

  static GoogleSignIn? _configuredGoogleSignIn() {
    const clientId = GoogleAuthConfig.clientId;
    const serverClientId = GoogleAuthConfig.serverClientId;
    final configured = kIsWeb
        ? clientId.isNotEmpty
        : defaultTargetPlatform == TargetPlatform.android
            ? serverClientId.isNotEmpty
            : clientId.isNotEmpty;
    if (!configured) return null;

    return GoogleSignIn(
      clientId: clientId.isEmpty ? null : clientId,
      serverClientId: kIsWeb || serverClientId.isEmpty ? null : serverClientId,
    );
  }

  bool get isConfigured => _googleSignIn != null;
  bool get usesWebButton => kIsWeb && isConfigured;

  Stream<String?> get idTokenEvents async* {
    final google = _googleSignIn;
    if (google == null) return;
    await for (final account in google.onCurrentUserChanged) {
      if (account == null) continue;
      yield await _tokenFromAccount(account);
    }
  }

  static Future<String?> _tokenFromAccount(GoogleSignInAccount? account) async {
    if (account == null) return null;
    return (await account.authentication).idToken;
  }

  Future<String?> idToken() async {
    final google = _googleSignIn;
    if (google == null) return null;
    try {
      final account = await google.signIn();
      final token =
          account == null ? null : (await account.authentication).idToken;
      if (token == null || token.isEmpty) {
        throw const GoogleAuthException(
            'Google did not return a sign-in token. Please try again.');
      }
      return token;
    } on PlatformException catch (error) {
      if (error.code == GoogleSignIn.kSignInCanceledError) return null;
      throw const GoogleAuthException(
          'Google sign-in failed. Please try again.');
    }
  }

  Future<void> signOut() async {
    await _googleSignIn?.signOut();
  }
}
