import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';

export 'package:google_maps_flutter/google_maps_flutter.dart' show LatLng;

/// Where the live map gets its key from.
///
/// * Android / iOS: the key lives in the platform project
///   (`AndroidManifest.xml` / `Info.plist`), not in Dart.
/// * Web: the JS API is loaded by `web/index.html`; pass the same key at build
///   time so the Dart side knows a map can be created:
///   `flutter build web --dart-define=GOOGLE_MAPS_API_KEY=...`
class MapConfig {
  MapConfig._();

  static const apiKey = String.fromEnvironment('GOOGLE_MAPS_API_KEY');

  static bool get _mobile =>
      !kIsWeb &&
      (defaultTargetPlatform == TargetPlatform.android || defaultTargetPlatform == TargetPlatform.iOS);

  /// False on desktop and on web builds without a key: `LiveMap` then draws its
  /// own dark preview surface instead of a broken map widget.
  static bool get enabled => kIsWeb ? apiKey.isNotEmpty : _mobile;

  /// Kampala city centre — the fallback camera target.
  static const kampala = LatLng(0.3476, 32.5825);

  /// Dark map styling that matches the app palette (graphite roads, muted labels).
  static const darkStyle = '''
[
  {"elementType":"geometry","stylers":[{"color":"#0b0d10"}]},
  {"elementType":"labels.text.fill","stylers":[{"color":"#767c84"}]},
  {"elementType":"labels.text.stroke","stylers":[{"color":"#0b0d10"}]},
  {"elementType":"labels.icon","stylers":[{"visibility":"off"}]},
  {"featureType":"administrative","elementType":"geometry.stroke","stylers":[{"color":"#1d2228"}]},
  {"featureType":"administrative.land_parcel","stylers":[{"visibility":"off"}]},
  {"featureType":"landscape.natural","elementType":"geometry","stylers":[{"color":"#0e1114"}]},
  {"featureType":"poi","elementType":"geometry","stylers":[{"color":"#121619"}]},
  {"featureType":"poi","elementType":"labels.text.fill","stylers":[{"color":"#5a6169"}]},
  {"featureType":"poi.business","stylers":[{"visibility":"off"}]},
  {"featureType":"poi.park","elementType":"geometry.fill","stylers":[{"color":"#0f1a14"}]},
  {"featureType":"road","elementType":"geometry.fill","stylers":[{"color":"#191d22"}]},
  {"featureType":"road","elementType":"geometry.stroke","stylers":[{"color":"#14171b"}]},
  {"featureType":"road.arterial","elementType":"geometry.fill","stylers":[{"color":"#1f242a"}]},
  {"featureType":"road.highway","elementType":"geometry.fill","stylers":[{"color":"#2a2f36"}]},
  {"featureType":"road.highway","elementType":"geometry.stroke","stylers":[{"color":"#333941"}]},
  {"featureType":"road","elementType":"labels.text.fill","stylers":[{"color":"#727880"}]},
  {"featureType":"transit","stylers":[{"visibility":"off"}]},
  {"featureType":"water","elementType":"geometry","stylers":[{"color":"#0a1219"}]},
  {"featureType":"water","elementType":"labels.text.fill","stylers":[{"color":"#42505a"}]}
]
''';
}

/// Haversine distance in kilometres between two points.
double distanceKm(LatLng a, LatLng b) {
  const earthKm = 6371.0;
  final dLat = _rad(b.latitude - a.latitude);
  final dLng = _rad(b.longitude - a.longitude);
  final h = math.pow(math.sin(dLat / 2), 2) +
      math.cos(_rad(a.latitude)) * math.cos(_rad(b.latitude)) * math.pow(math.sin(dLng / 2), 2);
  return 2 * earthKm * math.asin(math.min(1, math.sqrt(h.toDouble())));
}

double _rad(double deg) => deg * math.pi / 180;

/// Linear interpolation between two coordinates (used while a driver moves).
LatLng lerpLatLng(LatLng a, LatLng b, double t) => LatLng(
      a.latitude + (b.latitude - a.latitude) * t,
      a.longitude + (b.longitude - a.longitude) * t,
    );

/// Compass bearing (degrees) from [a] to [b].
double bearingDeg(LatLng a, LatLng b) {
  final dLng = _rad(b.longitude - a.longitude);
  final y = math.sin(dLng) * math.cos(_rad(b.latitude));
  final x = math.cos(_rad(a.latitude)) * math.sin(_rad(b.latitude)) -
      math.sin(_rad(a.latitude)) * math.cos(_rad(b.latitude)) * math.cos(dLng);
  return (math.atan2(y, x) * 180 / math.pi + 360) % 360;
}