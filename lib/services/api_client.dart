import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;

/// Where the FuelConnect backend lives. Set it at build time:
///   flutter run  --dart-define=API_BASE_URL=http://10.0.2.2:8000/api/v1      (Android emulator â†’ your laptop)
///   flutter build apk --dart-define=API_BASE_URL=https://api.fuelconnect.example/api/v1
class ApiConfig {
  static const baseUrl = String.fromEnvironment('API_BASE_URL', defaultValue: 'http://10.0.2.2:8000/api/v1');

  /// Release builds refuse to talk to a server over plain HTTP.
  static void assertSecure() {
    if (kReleaseMode && !baseUrl.startsWith('https://')) {
      throw StateError('Release builds require an https:// API_BASE_URL (got "$baseUrl").');
    }
  }
}

class ApiException implements Exception {
  final String message;
  final int? status;
  const ApiException(this.message, [this.status]);
  @override
  String toString() => message;
}

/// Thin JSON client: bearer token in the platform keystore (Keychain / EncryptedSharedPreferences),
/// timeouts, and friendly errors taken from the API's `message` / `errors`.
class ApiClient {
  ApiClient._();
  static final ApiClient instance = ApiClient._();

  static const _tokenKey = 'fc_api_token';
  static const _timeout = Duration(seconds: 20);

  final _storage = const FlutterSecureStorage(aOptions: AndroidOptions(encryptedSharedPreferences: true));
  final http.Client _http = http.Client();
  String? _token;

  /// Called when the server says the token is no longer valid (expired, revoked, account suspended).
  void Function()? onUnauthorized;

  bool get hasToken => _token != null;

  Future<void> init() async {
    ApiConfig.assertSecure();
    try {
      _token = await _storage.read(key: _tokenKey);
    } catch (_) {
      _token = null;
    }
  }

  Future<void> saveToken(String token) async {
    _token = token;
    await _storage.write(key: _tokenKey, value: token);
  }

  Future<void> clearToken() async {
    _token = null;
    try {
      await _storage.delete(key: _tokenKey);
    } catch (_) {}
  }

  Future<dynamic> get(String path, {Map<String, String>? query}) => _send('GET', path, query: query);
  Future<dynamic> post(String path, {Object? body}) => _send('POST', path, body: body);
  Future<dynamic> put(String path, {Object? body}) => _send('PUT', path, body: body);
  Future<dynamic> delete(String path) => _send('DELETE', path);

  Future<dynamic> _send(String method, String path, {Map<String, String>? query, Object? body}) async {
    final uri = Uri.parse('${ApiConfig.baseUrl}$path').replace(queryParameters: query);
    final headers = <String, String>{
      'Accept': 'application/json',
      'Content-Type': 'application/json',
      if (_token != null) 'Authorization': 'Bearer $_token',
    };

    http.Response res;
    try {
      final req = http.Request(method, uri)..headers.addAll(headers);
      if (body != null) req.body = jsonEncode(body);
      res = await http.Response.fromStream(await _http.send(req).timeout(_timeout));
    } on TimeoutException {
      throw const ApiException('The server is taking too long to respond. Please try again.');
    } catch (_) {
      throw const ApiException('We couldnâ€™t reach FuelConnect. Check your connection and try again.');
    }

    dynamic json;
    if (res.body.isNotEmpty) {
      try {
        json = jsonDecode(utf8.decode(res.bodyBytes));
      } catch (_) {
        json = null;
      }
    }

    if (res.statusCode >= 200 && res.statusCode < 300) return json;

    if (res.statusCode == 401) {
      await clearToken();
      onUnauthorized?.call();
    }
    throw ApiException(_messageFrom(json, res.statusCode), res.statusCode);
  }

  String _messageFrom(dynamic json, int status) {
    if (json is Map) {
      final errors = json['errors'];
      if (errors is Map && errors.isNotEmpty) {
        final first = errors.values.first;
        if (first is List && first.isNotEmpty) return first.first.toString();
      }
      final m = json['message'];
      if (m is String && m.isNotEmpty) return m;
    }
    if (status == 429) return 'Too many attempts. Please wait a moment and try again.';
    if (status == 426) return 'A secure (HTTPS) connection is required.';
    if (status >= 500) return 'Something went wrong on our side. Please try again shortly.';
    return 'Something went wrong. Please try again.';
  }
}
