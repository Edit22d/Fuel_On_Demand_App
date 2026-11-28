import 'package:flutter/material.dart';
import 'data.dart';
import 'icons.dart';
import 'map_style.dart';
import 'theme.dart';

enum Screen {
  splash, onboarding, login, signup, forgot, otp, newPassword, locationAccess,
  home, partners, station, fuel, vehicle, checkout, payment, tracking, success,
  orders, orderDetail, wallet, rewards, notifications, profile, addresses,
  vehicles, support, safety,
  // Added from the Figma prototype (customer extras + rider app).
  orderConfirmation, cancelOrder, editProfile, appSettings,
  riderRegistration, riderLogin, riderDashboard, riderDeliveries, riderRequest,
  riderDecision, riderNavigation, riderPickup, riderDelivery, riderEarnings,
}

class AppState extends ChangeNotifier {
  // ----- navigation --------------------------------------------------------
  Screen current = Screen.splash;
  final List<Screen> _stack = [Screen.splash];
  bool get canGoBack => _stack.length > 1;

  void go(Screen s, {bool root = false, bool replace = false}) {
    if (root) {
      _stack
        ..clear()
        ..add(s);
    } else if (replace) {
      _stack[_stack.length - 1] = s;
    } else {
      _stack.add(s);
    }
    current = s;
    notifyListeners();
  }

  bool back() {
    if (_stack.length > 1) {
      _stack.removeLast();
      current = _stack.last;
      notifyListeners();
      return true;
    }
    return false;
  }

  void backOr(Screen fallback) {
    if (!back()) go(fallback, root: true);
  }

  // ----- location ----------------------------------------------------------
  String location = 'Kololo, Kampala';
  bool pushOn = true;
  bool locationOn = true;

  /// Last GPS fix taken by the app (null until the device answers).
  double? lat, lng;
  DateTime? locatedAt;
  bool locating = false;

  /// Delivery pin — set from GPS, the map, or a saved place.
  double? deliveryLat, deliveryLng;

  LatLng? get geoPoint => (lat == null || lng == null) ? null : LatLng(lat!, lng!);
  LatLng? get deliveryPoint =>
      (deliveryLat == null || deliveryLng == null) ? null : LatLng(deliveryLat!, deliveryLng!);

  /// Origin used when there is no GPS fix yet (Kampala city centre).
  LatLng get fallbackPoint => geoPoint ?? MapConfig.kampala;

  void setGeo(double la, double ln, {String? label}) {
    lat = la;
    lng = ln;
    locatedAt = DateTime.now();
    if (label != null && label.trim().isNotEmpty) location = label.trim();
    deliveryLat ??= la;
    deliveryLng ??= ln;
    notifyListeners();
  }

  void setDeliveryPoint(double la, double ln, {String? address}) {
    deliveryLat = la;
    deliveryLng = ln;
    if (address != null && address.trim().isNotEmpty) deliveryAddress = address.trim();
    notifyListeners();
  }

  // ----- live order --------------------------------------------------------
  /// Id of the order the customer is tracking (also used by the orders list).
  String? activeOrderId;
  String get orderIdLabel => activeOrderId ?? '—';

  /// Local reference for a brand new order. The backend returns the canonical
  /// id (`POST /orders`) and tracking swaps to it automatically.
  String newOrderId() {
    final n = DateTime.now().millisecondsSinceEpoch % 900000;
    activeOrderId = 'FC-${100000 + n}';
    return activeOrderId!;
  }

  // ----- theme -------------------------------------------------------------
  ThemeMode themeMode = ThemeMode.dark;
  bool get isDark => themeMode == ThemeMode.dark;

  void setDarkMode(bool value) {
    themeMode = value ? ThemeMode.dark : ThemeMode.light;
    FC.dark = value;
    notifyListeners();
    rebuildApp();
  }

  void toggleTheme() => setDarkMode(!isDark);

  // ----- order builder -----------------------------------------------------
  static const prices = {'Petrol': 5180, 'Diesel': 4960, 'Power': 6450};
  static const deliveryFee = 8000;
  static const serviceFee = 2500;

  String fuelType = 'Petrol';
  int litres = 35;
  String vehicleId = 'rav4';
  bool scheduled = false;
  TimeOfDay? scheduledAt;
  String deliveryAddress = 'Acacia Mall, Kisementi';
  String deliveryNote = '';
  String payId = 'airtel';
  bool stationSaved = false;

  int get fuelTotal => litres * prices[fuelType]!;
  int get orderTotal => fuelTotal + deliveryFee + serviceFee;
  String get productName =>
      fuelType == 'Petrol' ? 'Premium petrol' : (fuelType == 'Diesel' ? 'Ultra diesel' : 'Power');
  String fuelClass(String t) => t == 'Diesel' ? 'Diesel' : 'Petrol';

  final List<Vehicle> vehicles = [
    const Vehicle(id: 'rav4', name: 'Toyota RAV4', plate: 'UBP 482M', fuel: 'Petrol', color: 'Black', tank: '60L', visual: 'RAV4'),
    const Vehicle(id: 'hilux', name: 'Toyota Hilux', plate: 'UBN 117Q', fuel: 'Diesel', color: 'Silver', tank: '80L', visual: 'HILUX'),
  ];
  Vehicle get selectedVehicle =>
      vehicles.firstWhere((v) => v.id == vehicleId, orElse: () => vehicles.first);

  final List<Place> places = [
    const Place('Home', 'Plot 18, Kira Road, Bukoto'),
    const Place('Office', 'Rwenzori Towers, Nakasero'),
    const Place('Gym', 'Acacia Mall, Kisementi'),
  ];

  // Demo merchant codes: replace with your real ones when you have them.
  final List<PayMethod> payMethods = [
    const PayMethod(id: 'airtel', title: 'Airtel Merchant Code', caption: 'Merchant code 123456', badge: 'A', badgeBg: Color(0xFFE9222B), badgeFg: Colors.white),
    const PayMethod(id: 'mtn', title: 'MTN Merchant Code', caption: 'Merchant code 654321', badge: 'MTN', badgeBg: Color(0xFFFFCB05), badgeFg: Color(0xFF171717)),
    const PayMethod(id: 'cash', title: 'Cash on delivery', caption: 'Pay your delivery partner', icon: IconName.card),
  ];
  PayMethod get selectedPay => payMethods.firstWhere((m) => m.id == payId, orElse: () => payMethods.first);

  // ----- wallet / rewards --------------------------------------------------
  int walletBalance = 480000;
  int points = 2450;
  static const nextTierPoints = 3000;
  final List<WalletTx> txs = [
    const WalletTx('Fuel order', 'Stabex Kira Road', -191800),
    const WalletTx('Wallet top up', 'MTN Mobile Money', 300000),
    const WalletTx('Fuel order', 'Shell Lugogo', -153500),
  ];

  /// Returns an error message, or null when the payment can proceed.
  String? charge() {
    final total = orderTotal;
    if (payId == 'wallet') {
      if (walletBalance < total) return 'Your wallet balance is too low. Top up or pick another method.';
      walletBalance -= total;
    }
    txs.insert(0, WalletTx('Fuel order', 'Stabex Kira Road', -total));
    return null;
  }

  void completeDelivery() => points += orderTotal ~/ 1000;

  void topUp(int amount) {
    walletBalance += amount;
    txs.insert(0, WalletTx('Wallet top up', 'MTN Mobile Money', amount));
  }

  // ----- notifications -----------------------------------------------------
  final List<Notice> notices = [
    Notice(IconName.truck, 'Your fuel is on the way', 'Marcus has collected your order and will arrive in 12–16 minutes.', 'Now', true),
    Notice(IconName.check, 'Payment confirmed', 'Your payment of UGX 191,800 was successful.', '4 min', true),
    Notice(IconName.fuel, 'Prices dropped near you', 'Petrol is now UGX 5,180/L at Stabex Kira Road.', '2 hr', false),
    Notice(IconName.shield, 'Safety check complete', 'Your delivery partner has passed the pre-trip safety check.', 'Yesterday', false),
  ];
}

final app = AppState();