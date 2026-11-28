import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import '../core/core.dart';
import '../core/rider_state.dart';
import '../services/tracking_service.dart';
import 'sheets.dart';

// ===========================================================================
// Saved places
// ===========================================================================
class AddressesScreen extends StatelessWidget {
  final Go go;
  const AddressesScreen({super.key, required this.go});

  @override
  Widget build(BuildContext context) {
    return AppPage(
      header: PageHeader(title: 'Saved places', goBack: () => app.backOr(Screen.profile)),
      body: Narrow(gap: 12, padTop: 20, children: [
        Panel(
          child: Row(children: [
            IconBox(IconName.location),
            const SizedBox(width: 12),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                FcText('Current location', kind: Tx.subtitle),
                FcText(app.location, kind: Tx.caption, color: FC.muted),
              ]),
            ),
          ]),
        ),
        Panel(
          child: Row(children: [
            IconBox(IconName.home),
            const SizedBox(width: 12),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                FcText('Delivery address', kind: Tx.subtitle),
                FcText(app.deliveryAddress, kind: Tx.caption, color: FC.muted),
              ]),
            ),
          ]),
        ),
      ]),
    );
  }
}

// ===========================================================================
// My vehicles
// ===========================================================================
class VehiclesScreen extends StatefulWidget {
  final Go go;
  const VehiclesScreen({super.key, required this.go});
  @override
  State<VehiclesScreen> createState() => _VehiclesScreenState();
}

class _VehiclesScreenState extends State<VehiclesScreen> {
  @override
  Widget build(BuildContext context) {
    return AppPage(
      header: PageHeader(title: 'My vehicles', goBack: () => app.backOr(Screen.profile)),
      body: Narrow(gap: 12, padTop: 20, children: [
        for (final v in app.vehicles)
          Tap(
            onTap: () => setState(() => app.vehicleId = v.id),
            child: Panel(
              border: app.vehicleId == v.id ? FC.gold : null,
              child: Row(children: [
                IconBox(IconName.truck),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    FcText(v.name, kind: Tx.subtitle),
                    FcText('${v.plate} · ${v.fuel} · ${v.color} · ${v.tank}', kind: Tx.caption, color: FC.muted),
                  ]),
                ),
                RadioDot(selected: app.vehicleId == v.id),
              ]),
            ),
          ),
      ]),
    );
  }
}

// ===========================================================================
// Help centre
// ===========================================================================
class SupportScreen extends StatelessWidget {
  final Go go;
  const SupportScreen({super.key, required this.go});

  static const _phone = '+256800200300';
  static const _phoneLabel = '+256 800 200 300';

  Widget _option(IconName icon, String title, String body, VoidCallback onTap, {Color? tint, bool last = false}) => Tap(
        onTap: onTap,
        child: Container(
          constraints: const BoxConstraints(minHeight: 64),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          decoration: BoxDecoration(border: last ? null : Border(bottom: BorderSide(color: FC.line))),
          child: Row(children: [
            IconBox(icon, color: tint),
            const SizedBox(width: 12),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                FcText(title, kind: Tx.label),
                const SizedBox(height: 2),
                FcText(body, kind: Tx.caption, color: FC.muted),
              ]),
            ),
            const SizedBox(width: 10),
            Ic(IconName.chevron, size: 18, color: FC.dim),
          ]),
        ),
      );

  void _cancelOrder(BuildContext context) {
    if (tracker.active) {
      go(Screen.cancelOrder);
    } else {
      toast(context, 'No order is in progress right now. Start a delivery first.');
    }
  }

  void _rejectOrder(BuildContext context) {
    if (rider.signedIn) {
      go(Screen.riderDeliveries);
    } else {
      showSupportChat(context, topic: 'I’d like to reject an order.');
    }
  }

  Future<void> _callSupport(BuildContext context) async {
    var ok = false;
    try {
      ok = await launchUrl(Uri(scheme: 'tel', path: _phone));
    } catch (_) {
      ok = false;
    }
    if (!context.mounted || ok) return;
    toast(context, 'Could not open the dialler. Message us in chat instead.');
  }

  @override
  Widget build(BuildContext context) {
    // Support is docked in the customer navigation. A signed-in delivery
    // partner keeps their chrome-free layout instead.
    final nav = !rider.signedIn;
    return AppPage(
      nav: nav,
      navCurrent: nav ? Screen.support : null,
      go: nav ? go : null,
      header: PageHeader(title: 'Help centre', goBack: () => app.backOr(Screen.home)),
      body: Narrow(gap: 12, padTop: 20, children: [
        RoundFeature(IconName.phone),
        FcText('How can we help?', kind: Tx.title, align: TextAlign.center),
        FcText('Reach us any time, or sort out a delivery yourself.', kind: Tx.body, color: FC.muted, align: TextAlign.center),
        const SizedBox(height: 8),
        Align(alignment: Alignment.centerLeft, child: FcText('TALK TO US', kind: Tx.label, color: FC.gold)),
        Container(
          clipBehavior: Clip.antiAlias,
          decoration: BoxDecoration(color: FC.surface, borderRadius: BorderRadius.circular(18), border: Border.all(color: FC.line)),
          child: Column(children: [
            _option(IconName.phone, 'Call support', 'Toll-free on $_phoneLabel.', () => _callSupport(context), tint: FC.green),
            _option(IconName.chat, 'Chat with support', 'Message an agent about any delivery.', () => showSupportChat(context), last: true),
          ]),
        ),
        const SizedBox(height: 6),
        Align(alignment: Alignment.centerLeft, child: FcText('MANAGE AN ORDER', kind: Tx.label, color: FC.gold)),
        Container(
          clipBehavior: Clip.antiAlias,
          decoration: BoxDecoration(color: FC.surface, borderRadius: BorderRadius.circular(18), border: Border.all(color: FC.line)),
          child: Column(children: [
            _option(IconName.orders, 'Cancel an order', 'Stop a delivery that hasn’t arrived yet.', () => _cancelOrder(context), tint: FC.danger),
            _option(IconName.minus, 'Reject an order', 'Decline a delivery request you can’t take.', () => _rejectOrder(context), last: true),
          ]),
        ),
        FcText('Support is available 24/7 for active deliveries.', kind: Tx.caption, color: FC.muted, align: TextAlign.center),
      ]),
    );
  }
}

// ===========================================================================
// Safety centre
// ===========================================================================
class SafetyScreen extends StatelessWidget {
  final Go go;
  const SafetyScreen({super.key, required this.go});

  @override
  Widget build(BuildContext context) {
    return AppPage(
      header: PageHeader(title: 'Safety centre', goBack: () => app.backOr(Screen.profile)),
      body: Narrow(gap: 12, padTop: 20, children: [
        SafetyNote(title: 'Verified delivery partners', body: 'Every delivery partner is checked before they can accept orders.'),
        SafetyNote(title: 'Pre-trip safety check', body: 'Partners complete a safety check before collecting your fuel.'),
      ]),
    );
  }
}