import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';

import 'api_client.dart';

/// Lifecycle of a delivery, mirrored by the backend `status` field.
enum OrderStage { confirmed, collecting, enRoute, arriving, delivered, cancelled }

OrderStage stageFromApi(String? value) {
  switch (value) {
    case 'collecting':
    case 'loading':
      return OrderStage.collecting;
    case 'en_route':
    case 'on_the_way':
      return OrderStage.enRoute;
    case 'arriving':
    case 'nearby':
      return OrderStage.arriving;
    case 'delivered':
    case 'completed':
      return OrderStage.delivered;
    case 'cancelled':
    case 'canceled':
      return OrderStage.cancelled;
    default:
      return OrderStage.confirmed;
  }
}

extension OrderStageX on OrderStage {
  /// 0..3 index used by the progress timeline.
  int get step => switch (this) {
        OrderStage.confirmed => 0,
        OrderStage.collecting => 1,
        OrderStage.enRoute => 2,
        OrderStage.arriving => 3,
        OrderStage.delivered => 3,
        OrderStage.cancelled => 0,
      };

  String get label => switch (this) {
        OrderStage.confirmed => 'Order confirmed',
        OrderStage.collecting => 'Fuel collected',
        OrderStage.enRoute => 'On the way to you',
        OrderStage.arriving => 'Arriving at your location',
        OrderStage.delivered => 'Delivery complete',
        OrderStage.cancelled => 'Order cancelled',
      };

  String get headline => switch (this) {
        OrderStage.confirmed => 'We are preparing your order',
        OrderStage.collecting => 'Fuel is being loaded',
        OrderStage.enRoute => 'Fuel is on the way',
        OrderStage.arriving => 'Your partner is nearby',
        OrderStage.delivered => 'Delivery complete',
        OrderStage.cancelled => 'Order cancelled',
      };

  bool get active => this != OrderStage.delivered && this != OrderStage.cancelled;
}

/// The delivery partner assigned to an order.
class Driver {
  final String name;
  final double rating;
  final String phone;
  final String vehicle;
  final String plate;

  const Driver({
    required this.name,
    this.rating = 0,
    this.phone = '',
    this.vehicle = '',
    this.plate = '',
  });

  String get initials {
    final parts = name.trim().split(RegExp(r'\s+')).where((p) => p.isNotEmpty).toList();
    if (parts.isEmpty) return '?';
    if (parts.length == 1) return parts.first.substring(0, 1).toUpperCase();
    return (parts.first.substring(0, 1) + parts.last.substring(0, 1)).toUpperCase();
  }

  String get caption => [
        if (vehicle.isNotEmpty) vehicle,
        if (plate.isNotEmpty) plate,
        if (rating > 0) rating.toStringAsFixed(1),
      ].join(' · ');

  factory Driver.fromJson(Map<String, dynamic> j) => Driver(
        name: (j['name'] ?? 'Delivery partner').toString(),
        rating: (j['rating'] as num?)?.toDouble() ?? 0,
        phone: (j['phone'] ?? '').toString(),
        vehicle: (j['vehicle'] ?? '').toString(),
        plate: (j['plate'] ?? '').toString(),
      );
}

/// Everything the tracking UI needs for one order. Parsed from the backend
/// response described in [TrackingService].
class OrderTracking {
  final String orderId;
  final OrderStage stage;
  final Driver? driver;
  final LatLng? driverPoint;
  final LatLng? pickup;
  final LatLng? destination;
  final List<LatLng> route;
  final int litres;
  final double litresLoaded;
  final double litresDispensed;
  final int etaMinutes;
  final DateTime updatedAt;

  const OrderTracking({
    required this.orderId,
    required this.stage,
    this.driver,
    this.driverPoint,
    this.pickup,
    this.destination,
    this.route = const [],
    required this.litres,
    this.litresLoaded = 0,
    this.litresDispensed = 0,
    this.etaMinutes = 0,
    required this.updatedAt,
  });

  double get deliveredFraction => litres == 0 ? 0 : (litresDispensed / litres).clamp(0.0, 1.0);

  /// 0..1 along the driver's route.
  double get routeProgress {
    final d = destination;
    final p = driverPoint;
    final o = pickup;
    if (d == null || p == null || o == null) return 0;
    final total = _km(o, d);
    if (total <= 0.001) return 1;
    return (1 - _km(p, d) / total).clamp(0.0, 1.0);
  }

  OrderTracking copyWith({
    OrderStage? stage,
    Driver? driver,
    LatLng? driverPoint,
    List<LatLng>? route,
    double? litresLoaded,
    double? litresDispensed,
    int? etaMinutes,
    DateTime? updatedAt,
  }) =>
      OrderTracking(
        orderId: orderId,
        stage: stage ?? this.stage,
        driver: driver ?? this.driver,
        driverPoint: driverPoint ?? this.driverPoint,
        pickup: pickup,
        destination: destination,
        route: route ?? this.route,
        litres: litres,
        litresLoaded: litresLoaded ?? this.litresLoaded,
        litresDispensed: litresDispensed ?? this.litresDispensed,
        etaMinutes: etaMinutes ?? this.etaMinutes,
        updatedAt: updatedAt ?? this.updatedAt,
      );

  /// Backend payload (`GET /orders/{id}/tracking`).
  factory OrderTracking.fromJson(Map<String, dynamic> j, {required OrderSeed seed}) {
    LatLng? point(dynamic raw) {
      if (raw is Map) {
        final lat = (raw['lat'] as num?)?.toDouble();
        final lng = (raw['lng'] ?? raw['lon']) as num?;
        if (lat != null && lng != null) return LatLng(lat, lng.toDouble());
      }
      return null;
    }

    final route = <LatLng>[
      for (final p in (j['route'] as List? ?? const [])) if (point(p) != null) point(p)!,
    ];

    return OrderTracking(
      orderId: (j['order_id'] ?? j['id'] ?? seed.orderId).toString(),
      stage: stageFromApi((j['status'] ?? j['stage'])?.toString()),
      driver: j['driver'] is Map ? Driver.fromJson(Map<String, dynamic>.from(j['driver'] as Map)) : null,
      driverPoint: point(j['location'] ?? j['driver_location']) ??
          LatLng((j['lat'] as num?)?.toDouble() ?? seed.pickup.latitude,
              (j['lng'] as num?)?.toDouble() ?? seed.pickup.longitude),
      pickup: point(j['pickup']) ?? seed.pickup,
      destination: point(j['destination']) ?? seed.destination,
      route: route,
      litres: ((j['litres'] as num?)?.round()) ?? seed.litres,
      litresLoaded: (j['litres_loaded'] as num?)?.toDouble() ?? 0,
      litresDispensed: (j['litres_dispensed'] as num?)?.toDouble() ?? 0,
      etaMinutes: ((j['eta_minutes'] ?? j['eta']) as num?)?.round() ?? 0,
      updatedAt: DateTime.tryParse((j['updated_at'] ?? '').toString()) ?? DateTime.now(),
    );
  }
}

/// Minimum order information needed to open the tracking screen.
class OrderSeed {
  final String orderId;
  final int litres;
  final LatLng pickup;
  final LatLng destination;
  final String stationName;
  final String product;

  const OrderSeed({
    required this.orderId,
    required this.litres,
    required this.pickup,
    required this.destination,
    required this.stationName,
    required this.product,
  });
}

/// Live order + fuel tracking.
///
/// Backend contract (polled every [pollEvery], swap `_poll` for a WebSocket
/// later without touching the UI):
///
///   GET  {baseUrl}/orders/{orderId}/tracking
///   {
///     "order_id": "FC-29841",
///     "status": "en_route",             // confirmed | collecting | en_route | arriving | delivered | cancelled
///     "eta_minutes": 12,
///     "driver": {"name": "Marcus K.", "rating": 4.9, "phone": "+256700123456",
///                "vehicle": "Toyota Hiace", "plate": "UBH 001A"},
///     "lat": 0.3421, "lng": 32.5891,    // driver position right now
///     "pickup":      {"lat": .., "lng": ..},
///     "destination": {"lat": .., "lng": ..},
///     "route": [{"lat": .., "lng": ..}, ...],
///     "litres": 35, "litres_loaded": 35, "litres_dispensed": 0,
///     "updated_at": "2026-11-26T18:42:11Z"
///   }
///
///   POST {baseUrl}/orders/{orderId}/cancel
///   POST {baseUrl}/orders/{orderId}/delivered
///
/// Until the API answers (no token, no network, backend not built yet) the
/// service runs a clearly-labelled offline preview so the map, GPS and fuel
/// gauges still animate. `isLive` switches to true the moment real data lands.
class TrackingService extends ChangeNotifier {
  static const pollEvery = Duration(seconds: 6);
  static const previewTick = Duration(milliseconds: 900);
  static const previewMinutes = 14;

  OrderTracking? order;
  OrderSeed? _seed;

  bool loading = false;
  bool isLive = false;
  String? error;
  DateTime? lastSync;

  Timer? _poll;
  Timer? _ticker;
  double _preview = 0; // 0..1 along the simulated route
  bool _disposed = false;

  bool get hasOrder => order != null;
  bool get active => order?.stage.active ?? false;

  /// Opens tracking for [seed]. Safe to call again for another order.
  Future<void> start(OrderSeed seed) async {
    _seed = seed;
    isLive = false;
    error = null;
    _preview = 0;
    order = _previewSnapshot();
    notifyListeners();

    _ticker?.cancel();
    _ticker = Timer.periodic(previewTick, (_) => _advancePreview());
    _poll?.cancel();
    _poll = Timer.periodic(pollEvery, (_) => refresh());
    await refresh();
  }

  void stop() {
    _poll?.cancel();
    _ticker?.cancel();
    _poll = null;
    _ticker = null;
  }

  /// Pulls one snapshot from the backend. Never throws.
  Future<void> refresh() async {
    final seed = _seed;
    if (seed == null || _disposed) return;
    if (!ApiClient.instance.hasToken) return; // nothing to authenticate with yet

    loading = true;
    notifyListeners();
    try {
      final json = await ApiClient.instance.get('/orders/${seed.orderId}/tracking');
      if (json is Map<String, dynamic>) {
        final remote = OrderTracking.fromJson(json, seed: seed);
        order = remote.route.isEmpty
            ? remote.copyWith(route: [if (remote.pickup != null) remote.pickup!, if (remote.driverPoint != null) remote.driverPoint!, if (remote.destination != null) remote.destination!])
            : remote;
        isLive = true;
        error = null;
        lastSync = DateTime.now();
        _ticker?.cancel();
        _ticker = null;
      }
    } on ApiException catch (e) {
      error = e.message;
    } catch (_) {
      error = 'Tracking is reconnecting…';
    } finally {
      if (!_disposed) {
        loading = false;
        notifyListeners();
      }
    }
  }

  /// Customer confirms the fuel was dispensed. Hits the API when live.
  Future<void> confirmDelivery() async {
    final seed = _seed;
    if (isLive && seed != null && ApiClient.instance.hasToken) {
      try {
        await ApiClient.instance.post('/orders/${seed.orderId}/delivered');
        await refresh();
        return;
      } on ApiException catch (e) {
        error = e.message;
      }
    }
    order = order?.copyWith(
      stage: OrderStage.delivered,
      litresDispensed: order?.litres.toDouble(),
      etaMinutes: 0,
      updatedAt: DateTime.now(),
    );
    _ticker?.cancel();
    notifyListeners();
  }

  Future<void> cancel() async {
    final seed = _seed;
    if (isLive && seed != null && ApiClient.instance.hasToken) {
      try {
        await ApiClient.instance.post('/orders/${seed.orderId}/cancel');
      } on ApiException catch (e) {
        error = e.message;
      }
    }
    order = order?.copyWith(stage: OrderStage.cancelled, etaMinutes: 0, updatedAt: DateTime.now());
    stop();
    notifyListeners();
  }

  // -------------------------------------------------------------------------
  // Offline preview
  // -------------------------------------------------------------------------
  void _advancePreview() {
    if (isLive || _disposed) return;
    _preview = math.min(1, _preview + 0.011);
    order = _previewSnapshot();
    notifyListeners();
  }

  OrderTracking _previewSnapshot() {
    final seed = _seed!;
    final route = _seedRoute(seed);
    final t = _preview;

    final stage = switch (t) {
      < .10 => OrderStage.confirmed,
      < .26 => OrderStage.collecting,
      < .84 => OrderStage.enRoute,
      < 1 => OrderStage.arriving,
      _ => OrderStage.delivered,
    };

    final along = ((t - .26) / .74).clamp(0.0, 1.0);
    final point = _along(route, along);
    final loaded = stage == OrderStage.confirmed ? 0.0 : seed.litres * ((t - .10) / .16).clamp(0.0, 1.0);
    final dispensed = stage == OrderStage.arriving
        ? seed.litres * ((t - .84) / .16).clamp(0.0, 1.0)
        : (stage == OrderStage.delivered ? seed.litres.toDouble() : 0.0);
    final eta = ((1 - t) * previewMinutes).ceil();

    return OrderTracking(
      orderId: seed.orderId,
      stage: stage,
      driver: const Driver(name: 'Marcus K.', rating: 4.9, phone: '+256700123456', vehicle: 'Toyota Hiace', plate: 'UBH 001A'),
      driverPoint: point,
      pickup: seed.pickup,
      destination: seed.destination,
      route: route,
      litres: seed.litres,
      litresLoaded: loaded,
      litresDispensed: dispensed,
      etaMinutes: eta,
      updatedAt: DateTime.now(),
    );
  }

  List<LatLng> _seedRoute(OrderSeed seed) {
    final a = seed.pickup, b = seed.destination;
    final mid = LatLng((a.latitude + b.latitude) / 2 + .0012, (a.longitude + b.longitude) / 2 - .0008);
    final mid2 = LatLng((a.latitude + b.latitude) / 2 - .0006, (a.longitude + b.longitude) / 2 + .0010);
    return [a, mid, mid2, b];
  }

  /// Walks a polyline and returns the point at fraction [t] of its length.
  LatLng _along(List<LatLng> pts, double t) {
    if (pts.isEmpty) return const LatLng(0, 0);
    if (pts.length == 1) return pts.first;
    final lengths = <double>[];
    var total = 0.0;
    for (var i = 1; i < pts.length; i++) {
      final d = _km(pts[i - 1], pts[i]);
      lengths.add(d);
      total += d;
    }
    if (total <= 0) return pts.last;
    var target = total * t;
    for (var i = 0; i < lengths.length; i++) {
      if (target <= lengths[i]) {
        final f = lengths[i] == 0 ? 0.0 : target / lengths[i];
        return LatLng(
          pts[i].latitude + (pts[i + 1].latitude - pts[i].latitude) * f,
          pts[i].longitude + (pts[i + 1].longitude - pts[i].longitude) * f,
        );
      }
      target -= lengths[i];
    }
    return pts.last;
  }

  @override
  void dispose() {
    _disposed = true;
    stop();
    super.dispose();
  }
}

double _km(LatLng a, LatLng b) {
  const r = 6371.0;
  final dLat = (b.latitude - a.latitude) * 0.017453292519943295;
  final dLng = (b.longitude - a.longitude) * 0.017453292519943295;
  final h = math.pow(math.sin(dLat / 2), 2) +
      math.cos(a.latitude * 0.017453292519943295) *
          math.cos(b.latitude * 0.017453292519943295) *
          math.pow(math.sin(dLng / 2), 2);
  return 2 * r * math.asin(math.min(1, math.sqrt(h.toDouble())));
}

final tracker = TrackingService();