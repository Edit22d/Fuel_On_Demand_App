import 'dart:async';
import 'package:flutter/foundation.dart';

enum FuelType { petrol, diesel }

/// Static info for the stations we currently serve. Add new stations here as you grow.
class LiveStation {
  final String id, name, brand, address, logoAsset;
  final double km, rating;
  final int reviews, etaMin, etaMax;
  final Map<FuelType, int> basePrice; // UGX per litre
  const LiveStation({
    required this.id,
    required this.name,
    required this.brand,
    required this.address,
    required this.logoAsset,
    required this.km,
    required this.rating,
    required this.reviews,
    required this.etaMin,
    required this.etaMax,
    required this.basePrice,
  });
}

const kLiveStations = <LiveStation>[
  LiveStation(
    id: 'stabex',
    name: 'Stabex Kira Road',
    brand: 'Stabex',
    address: 'Kira Road, Kampala Â· Open 24 hours',
    logoAsset: 'assets/images/logos/stabex.png',
    km: 1.8,
    rating: 4.9,
    reviews: 320,
    etaMin: 18,
    etaMax: 24,
    basePrice: {FuelType.petrol: 5180, FuelType.diesel: 4960},
  ),
  LiveStation(
    id: 'shell',
    name: 'Shell Jinja Road',
    brand: 'Shell',
    address: 'Jinja Road, Kampala Â· Open 24 hours',
    logoAsset: 'assets/images/logos/shell.png',
    km: 2.4,
    rating: 4.8,
    reviews: 275,
    etaMin: 20,
    etaMax: 27,
    basePrice: {FuelType.petrol: 5250, FuelType.diesel: 5020},
  ),
];

/// Live prices. Every order adds "demand pressure" which nudges that station's
/// price up; pressure then decays so prices drift back toward base.
///
/// This runs locally. To make it truly real-time across all users, have your
/// backend (Firestore / WebSocket) own the numbers and call [applyRemote].
class LivePrices extends ChangeNotifier {
  LivePrices() {
    _timer = Timer.periodic(const Duration(seconds: 20), (_) => _decay());
  }

  static const _litresPerStep = 100; // litres ordered per price step
  static const _stepUgx = 10; // UGX added per step
  static const _maxPremiumUgx = 300; // cap above base

  final Map<String, Map<FuelType, double>> _demand = {};
  final Map<String, Map<FuelType, int>> _remote = {};
  final Map<String, Map<FuelType, int>> _lastMove = {}; // for the up/down pill
  Timer? _timer;

  /// Station chosen on Home/Partners, read by the detail screen.
  String selectedId = kLiveStations.first.id;

  LiveStation byId(String id) => kLiveStations.firstWhere((s) => s.id == id);
  LiveStation get selected => byId(selectedId);

  int price(String id, FuelType f) {
    final r = _remote[id]?[f];
    if (r != null) return r;
    final base = byId(id).basePrice[f]!;
    final d = _demand[id]?[f] ?? 0;
    final prem = ((d / _litresPerStep).round() * _stepUgx).clamp(0, _maxPremiumUgx);
    return base + prem;
  }

  /// % difference vs. the station's base price.
  double changePct(String id, FuelType f) {
    final base = byId(id).basePrice[f]!;
    return (price(id, f) - base) / base * 100;
  }

  int lastMove(String id, FuelType f) => _lastMove[id]?[f] ?? 0;

  double get petrolAverage =>
      kLiveStations.map((s) => price(s.id, FuelType.petrol)).reduce((a, b) => a + b) / kLiveStations.length;

  /// Call this when an order is confirmed.
  void recordOrder(String stationId, FuelType fuel, double litres) {
    final before = price(stationId, fuel);
    final m = _demand.putIfAbsent(stationId, () => {});
    m[fuel] = (m[fuel] ?? 0) + litres;
    _lastMove.putIfAbsent(stationId, () => {})[fuel] = price(stationId, fuel) - before;
    notifyListeners();
  }

  /// Hook for server-pushed prices.
  void applyRemote(String stationId, FuelType fuel, int ugx) {
    final before = price(stationId, fuel);
    _remote.putIfAbsent(stationId, () => {})[fuel] = ugx;
    _lastMove.putIfAbsent(stationId, () => {})[fuel] = ugx - before;
    notifyListeners();
  }

  void _decay() {
    var changed = false;
    for (final e in _demand.values) {
      for (final f in e.keys.toList()) {
        if (e[f]! > 1) {
          e[f] = e[f]! * 0.92;
          changed = true;
        } else {
          e[f] = 0;
        }
      }
    }
    if (changed) notifyListeners();
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }
}

final livePrices = LivePrices();

String ugx(num v) {
  final s = v.round().toString();
  final b = StringBuffer();
  for (var i = 0; i < s.length; i++) {
    if (i > 0 && (s.length - i) % 3 == 0) b.write(',');
    b.write(s[i]);
  }
  return 'UGX $b';
}