import 'package:flutter/material.dart';
import 'icons.dart';

const kTotalGradient = LinearGradient(
  begin: Alignment.topLeft,
  end: Alignment.bottomRight,
  colors: [Color(0xFFE32135), Color(0xFF275AB6)],
);

class Slide {
  final String eyebrow, title, body, image;
  const Slide(this.eyebrow, this.title, this.body, this.image);
}

const kSlides = [
  Slide('ON-DEMAND DELIVERY', 'Fuel that meets you where you are.', 'Skip the station. Choose your fuel, pin your location, and we’ll handle the rest.', 'assets/images/station-hero.png'),
  Slide('LIVE PRICE COMPARISON', 'Better prices. Smarter refuels.', 'Compare verified stations nearby and always know exactly what you’ll pay.', 'assets/images/station-card.jpg'),
  Slide('SAFE & TRACKED', 'Every delivery, visible in real time.', 'From secure payment to arrival, follow your certified delivery partner every step.', 'assets/images/pump.png'),
];

class Vehicle {
  final String id, name, plate, fuel, color, tank, visual;
  const Vehicle({
    required this.id,
    required this.name,
    required this.plate,
    required this.fuel,
    this.color = '',
    this.tank = '',
    required this.visual,
  });
  String get selectCaption => [plate, fuel, if (color.isNotEmpty) color].join(' · ');
  String get listCaption => [plate, fuel, if (tank.isNotEmpty) '$tank tank'].join(' · ');
}

class Place {
  final String label, address;
  const Place(this.label, this.address);
}

class PayMethod {
  final String id, title, caption, badge;
  final IconName? icon;
  final Color? badgeBg, badgeFg;
  const PayMethod({
    required this.id,
    required this.title,
    required this.caption,
    this.badge = '',
    this.icon,
    this.badgeBg,
    this.badgeFg,
  });
}

class WalletTx {
  final String title, subtitle;
  final int amount;
  const WalletTx(this.title, this.subtitle, this.amount);
}

class Notice {
  final IconName icon;
  final String title, body, time;
  bool fresh;
  Notice(this.icon, this.title, this.body, this.time, this.fresh);
}

class HistoryOrder {
  final String date, station, product, price;
  const HistoryOrder(this.date, this.station, this.product, this.price);
}

const kHistory = [
  HistoryOrder('18 Jun 2025', 'Shell Lugogo', 'Diesel · 28L', 'UGX 153,500'),
  HistoryOrder('29 May 2025', 'Stabex Kira Road', 'Premium · 35L', 'UGX 191,800'),
  HistoryOrder('04 May 2025', 'TotalEnergies Ntinda', 'Petrol · 22L', 'UGX 124,400'),
];
