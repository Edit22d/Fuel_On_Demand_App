import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:geocoding/geocoding.dart' as geo;
import 'package:geolocator/geolocator.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';

/// Why a location request could or could not be served.
enum GeoStatus { unknown, granted, denied, deniedForever, serviceDisabled, unsupported }

/// One GPS reading, normalised for the rest of the app.
class LocationFix {
  final double lat;
  final double lng;
  final double accuracy; // metres
  final DateTime at;
  final String? label; // human readable, when reverse geocoding succeeds

  const LocationFix({
    required this.lat,
    required this.lng,
    this.accuracy = 0,
    required this.at,
    this.label,
  });

  LatLng get latLng => LatLng(lat, lng);
  LocationFix withLabel(String? value) =>
      LocationFix(lat: lat, lng: lng, accuracy: accuracy, at: at, label: value);

  /// Compact label for map chips: "Kira Road, Kampala".
  String get shortLabel {
    final l = label;
    if (l == null || l.isEmpty) return 'Pinned location';
    final parts = l.split(',').map((s) => s.trim()).where((s) => s.isNotEmpty).toList();
    if (parts.length <= 2) return parts.join(', ');
    return '${parts[parts.length - 3]}, ${parts[parts.length - 2]}';
  }
}

/// Device GPS: permission handling, one-shot fixes, a movement stream and
/// reverse geocoding. Every platform failure is converted into a [GeoStatus]
/// so screens can render a proper empty state instead of an exception.
class LocationService {
  LocationService._();
  static final LocationService instance = LocationService._();

  static const _watchDistance = 20; // metres between stream updates

  StreamSubscription<Position>? _sub;
  final _controllers = <String, StreamController<LocationFix>>{};

  LocationFix? last;
  GeoStatus status = GeoStatus.unknown;

  bool get _supported =>
      kIsWeb ||
      defaultTargetPlatform == TargetPlatform.android ||
      defaultTargetPlatform == TargetPlatform.iOS ||
      defaultTargetPlatform == TargetPlatform.macOS;

  bool get hasFix => last != null;

  /// Asks for permission (once) and reports the resulting state.
  Future<GeoStatus> ensure() async {
    if (!_supported) {
      status = GeoStatus.unsupported;
      return status;
    }
    try {
      if (!await Geolocator.isLocationServiceEnabled()) {
        status = GeoStatus.serviceDisabled;
        return status;
      }
      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      status = switch (permission) {
        LocationPermission.always || LocationPermission.whileInUse => GeoStatus.granted,
        LocationPermission.deniedForever => GeoStatus.deniedForever,
        _ => GeoStatus.denied,
      };
    } catch (_) {
      status = GeoStatus.unsupported;
    }
    return status;
  }

  /// One-shot fix. Returns null when permission is missing or the device fails.
  Future<LocationFix?> current({bool withLabel = true}) async {
    if (await ensure() != GeoStatus.granted) return null;
    try {
      final p = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(accuracy: LocationAccuracy.high, timeLimit: Duration(seconds: 12)),
      );
      var fix = _from(p);
      if (withLabel) fix = fix.withLabel(await describe(p.latitude, p.longitude));
      last = fix;
      return fix;
    } catch (_) {
      // Fall back to the last known point (common on emulators / indoors).
      try {
        final p = await Geolocator.getLastKnownPosition();
        if (p == null) return null;
        final fix = _from(p);
        last = fix;
        return fix;
      } catch (_) {
        return null;
      }
    }
  }

  /// Emits while the user moves. Only one native subscription is kept.
  Stream<LocationFix> watch() {
    const key = 'default';
    final existing = _controllers[key];
    if (existing != null && !existing.isClosed) return existing.stream;
    final controller = StreamController<LocationFix>.broadcast();
    _controllers[key] = controller;
    _startWatch(controller);
    return controller.stream;
  }

  Future<void> _startWatch(StreamController<LocationFix> controller) async {
    if (await ensure() != GeoStatus.granted) return;
    try {
      _sub = Geolocator.getPositionStream(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
          distanceFilter: _watchDistance,
        ),
      ).listen(
        (p) => controller.add(_from(p)),
        onError: (_) {},
      );
    } catch (_) {}
  }

  Future<void> stopWatch() async {
    await _sub?.cancel();
    _sub = null;
    for (final c in _controllers.values) {
      await c.close();
    }
    _controllers.clear();
  }

  LocationFix _from(Position p) => LocationFix(
        lat: p.latitude,
        lng: p.longitude,
        accuracy: p.accuracy,
        at: DateTime.now(),
      );

  /// Reverse geocodes a coordinate into "street, city, country".
  Future<String?> describe(double lat, double lng) async {
    if (!_supported) return null;
    try {
      final marks = await geo.Geocoding().placemarkFromCoordinates(lat, lng);
      if (marks.isEmpty) return null;
      final m = marks.first;
      final parts = <String>[
        if ((m.street ?? '').trim().isNotEmpty) m.street!.trim(),
        if ((m.subLocality ?? '').trim().isNotEmpty) m.subLocality!.trim(),
        if ((m.locality ?? '').trim().isNotEmpty) m.locality!.trim(),
        if ((m.country ?? '').trim().isNotEmpty) m.country!.trim(),
      ];
      return parts.isEmpty ? null : parts.join(', ');
    } catch (_) {
      return null;
    }
  }

  /// Straight-line distance in km to a point, or null without a fix.
  double? kmTo(LatLng other) {
    final f = last;
    if (f == null) return null;
    const r = 6371.0;
    final dLat = _rad(other.latitude - f.lat);
    final dLng = _rad(other.longitude - f.lng);
    final a = math.pow(math.sin(dLat / 2), 2) +
        math.cos(_rad(f.lat)) * math.cos(_rad(other.latitude)) * math.pow(math.sin(dLng / 2), 2);
    return 2 * r * math.asin(math.min(1, math.sqrt(a.toDouble())));
  }

  static double _rad(double d) => d * 0.017453292519943295;
}

final location = LocationService.instance;