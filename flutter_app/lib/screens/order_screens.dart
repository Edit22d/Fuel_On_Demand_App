import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import '../core/core.dart';
import '../services/location_service.dart';
import '../services/tracking_service.dart';
import 'browse_screens.dart';
import 'sheets.dart';

Widget _stepIntro(String step, String title, {String? body}) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      FcText(step, kind: Tx.label, color: FC.gold),
      const SizedBox(height: 9),
      FcText(title, kind: Tx.title),
      if (body != null) ...[const SizedBox(height: 9), FcText(body, color: FC.muted)],
    ]);

// ===========================================================================
// Fuel
// ===========================================================================
class FuelScreen extends StatefulWidget {
  final Go go;
  const FuelScreen({super.key, required this.go});
  @override
  State<FuelScreen> createState() => _FuelScreenState();
}

class _FuelScreenState extends State<FuelScreen> {
  Widget _round(IconName icon, VoidCallback onTap) => Tap(
        onTap: onTap,
        child: Container(
          width: 44,
          height: 44,
          decoration: BoxDecoration(shape: BoxShape.circle, color: const Color(0xFF191914), border: Border.all(color: const Color(0xFF4F4627))),
          child: Center(child: Ic(icon, color: FC.gold)),
        ),
      );

  @override
  Widget build(BuildContext context) {
    final l = app.litres;
    return AppPage(
      header: PageHeader(title: 'Build your order', goBack: () => app.backOr(Screen.station)),
      body: Narrow(gap: 22, children: [
        _stepIntro('STEP 1 OF 4 · FUEL', 'Select fuel type'),
        Row(children: [
          for (final f in ['Petrol', 'Diesel', 'Power'])
            Expanded(
              child: Padding(
                padding: EdgeInsets.only(right: f == 'Power' ? 0 : 9),
                child: Tap(
                  onTap: () => setState(() => app.fuelType = f),
                  child: Container(
                    padding: const EdgeInsets.symmetric(vertical: 15, horizontal: 5),
                    decoration: BoxDecoration(
                      color: app.fuelType == f ? al(FC.gold, .07) : FC.surface,
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: app.fuelType == f ? FC.gold : FC.line),
                    ),
                    child: Column(children: [
                      Ic(f == 'Power' ? IconName.drop : IconName.fuel, color: app.fuelType == f ? FC.gold : FC.muted),
                      const SizedBox(height: 7),
                      FcText(f, kind: Tx.label, color: app.fuelType == f ? FC.gold : FC.ink),
                      const SizedBox(height: 7),
                      FcText('UGX ${fmt(AppState.prices[f]!)}/L', kind: Tx.caption, color: FC.muted),
                    ]),
                  ),
                ),
              ),
            ),
        ]),
        Panel(
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: gapped([
            Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              FcText('QUANTITY', kind: Tx.label),
              FcText('How much should we deliver?', kind: Tx.caption, color: FC.muted),
            ]),
            Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
              _round(IconName.minus, () => setState(() => app.litres = math.max(5, l - 5))),
              Column(children: [
                Text('$l', style: fs(41.6, w: FontWeight.w700, h: 1.1, ls: -1)),
                Text('litres', style: fs(10.4, color: FC.muted)),
              ]),
              _round(IconName.plus, () => setState(() => app.litres = math.min(100, l + 5))),
            ]),
            ClipRRect(
              borderRadius: BorderRadius.circular(5),
              child: LinearProgressIndicator(value: l / 100, minHeight: 5, backgroundColor: FC.line, valueColor: AlwaysStoppedAnimation(FC.gold)),
            ),
            Row(children: [
              for (final a in [15, 25, 35, 50])
                Expanded(
                  child: Padding(
                    padding: EdgeInsets.only(right: a == 50 ? 0 : 7),
                    child: Tap(
                      onTap: () => setState(() => app.litres = a),
                      child: Container(
                        padding: const EdgeInsets.symmetric(vertical: 8),
                        alignment: Alignment.center,
                        decoration: BoxDecoration(color: const Color(0xFF0D0F12), borderRadius: BorderRadius.circular(9), border: Border.all(color: l == a ? FC.gold : FC.line)),
                        child: Text('${a}L', style: fs(10.4, color: l == a ? FC.gold : FC.muted, h: 1.3)),
                      ),
                    ),
                  ),
                ),
            ]),
          ], 20)),
        ),
        const SafetyNote(title: 'Certified safe delivery', body: 'Delivered in sealed, metered equipment by trained partners.'),
        Container(
          padding: const EdgeInsets.only(top: 20),
          decoration: BoxDecoration(border: Border(top: BorderSide(color: FC.line))),
          child: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
            Flexible(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                FcText('Estimated fuel total', kind: Tx.caption, color: FC.muted),
                FcText('UGX ${fmt(app.fuelTotal)}', kind: Tx.title),
              ]),
            ),
            FcButton('Continue', expand: false, trailingIcon: IconName.arrow, onTap: () => widget.go(Screen.vehicle)),
          ]),
        ),
      ]),
    );
  }
}

// ===========================================================================
// Vehicle
// ===========================================================================
class VehicleScreen extends StatefulWidget {
  final Go go;
  const VehicleScreen({super.key, required this.go});
  @override
  State<VehicleScreen> createState() => _VehicleScreenState();
}

class VehicleTile extends StatelessWidget {
  final Vehicle v;
  final bool selected;
  final String caption;
  final Widget trailing;
  final VoidCallback onTap;
  const VehicleTile({super.key, required this.v, required this.selected, required this.caption, required this.trailing, required this.onTap});
  @override
  Widget build(BuildContext context) => Tap(
        onTap: onTap,
        child: Container(
          constraints: const BoxConstraints(minHeight: 78),
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(color: selected ? al(FC.gold, .06) : FC.surface, borderRadius: BorderRadius.circular(12), border: Border.all(color: selected ? FC.gold : FC.line)),
          child: Row(children: [
            Container(
              width: 58,
              height: 42,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                gradient: const LinearGradient(begin: Alignment.topLeft, end: Alignment.bottomRight, colors: [Color(0xFF353A40), Color(0xFF171A1D)]),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Text(v.visual, style: fs(8.8, color: FC.gold, w: FontWeight.w900, ls: .7, h: 1)),
            ),
            const SizedBox(width: 12),
            Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [FcText(v.name, kind: Tx.subtitle), FcText(caption, kind: Tx.caption, color: FC.muted)])),
            const SizedBox(width: 12),
            trailing,
          ]),
        ),
      );
}

class _VehicleScreenState extends State<VehicleScreen> {
  @override
  Widget build(BuildContext context) {
    final v = app.selectedVehicle;
    final ok = app.fuelClass(app.fuelType) == v.fuel;
    return AppPage(
      header: PageHeader(title: 'Select vehicle', goBack: () => app.backOr(Screen.fuel)),
      body: Narrow(gap: 20, children: [
        _stepIntro('STEP 2 OF 4 · VEHICLE', 'Which vehicle are we fueling?', body: 'This helps your delivery partner identify you and confirm the correct fuel type.'),
        Column(children: gapped([
          for (final x in app.vehicles)
            VehicleTile(v: x, selected: x.id == v.id, caption: x.selectCaption, trailing: RadioDot(selected: x.id == v.id), onTap: () => setState(() => app.vehicleId = x.id)),
        ], 10)),
        Align(
          alignment: Alignment.centerLeft,
          child: Tap(
            onTap: () async {
              final added = await showAddVehicleSheet(context);
              if (added == true && mounted) setState(() => app.vehicleId = app.vehicles.last.id);
            },
            child: Padding(padding: const EdgeInsets.symmetric(vertical: 6), child: Row(mainAxisSize: MainAxisSize.min, children: [
              Ic(IconName.plus, color: FC.gold),
              const SizedBox(width: 6),
              Flexible(child: Text('Add another vehicle', style: fs(11.2, color: FC.gold, w: FontWeight.w700))),
            ])),
          ),
        ),
        ok
            ? SafetyNote(title: 'Fuel compatibility check', body: 'Selected vehicle uses ${v.fuel.toLowerCase()}. Your order is compatible.')
            : Container(
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(color: al(FC.danger, .06), borderRadius: BorderRadius.circular(12), border: Border.all(color: al(FC.danger, .25))),
                child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Ic(IconName.shield, color: FC.danger),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      FcText('Fuel compatibility check', kind: Tx.label, color: FC.danger),
                      const SizedBox(height: 3),
                      FcText('Selected vehicle uses ${v.fuel.toLowerCase()}, but your order is ${app.fuelType.toLowerCase()}. Change the fuel or pick another vehicle.', kind: Tx.caption, color: FC.muted),
                    ]),
                  ),
                ]),
              ),
        FcButton('Confirm vehicle', onTap: ok ? () => widget.go(Screen.checkout) : null),
      ]),
    );
  }
}

// ===========================================================================
// Delivery details
// ===========================================================================
class CheckoutScreen extends StatefulWidget {
  final Go go;
  const CheckoutScreen({super.key, required this.go});
  @override
  State<CheckoutScreen> createState() => _CheckoutScreenState();
}

class _CheckoutScreenState extends State<CheckoutScreen> {
  late final _note = TextEditingController(text: app.deliveryNote);

  @override
  void dispose() {
    app.deliveryNote = _note.text;
    _note.dispose();
    super.dispose();
  }

  Future<void> _pickTime() async {
    final t = await showTimePicker(context: context, initialTime: app.scheduledAt ?? TimeOfDay.fromDateTime(DateTime.now().add(const Duration(hours: 1))));
    if (t != null && mounted) {
      setState(() {
        app.scheduled = true;
        app.scheduledAt = t;
      });
    }
  }

  Widget _choice(IconName icon, String title, String sub, bool active, VoidCallback onTap) => Expanded(
        child: Tap(
          onTap: onTap,
          child: Container(
            constraints: const BoxConstraints(minHeight: 76),
            padding: const EdgeInsets.all(13),
            decoration: BoxDecoration(color: active ? al(FC.gold, .06) : FC.surface, borderRadius: BorderRadius.circular(12), border: Border.all(color: active ? FC.gold : FC.line)),
            child: Row(children: [
              Ic(icon, color: active ? FC.gold : FC.muted),
              const SizedBox(width: 12),
              Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [FcText(title, kind: Tx.label, color: active ? FC.gold : FC.ink), FcText(sub, kind: Tx.caption, color: FC.muted)])),
            ]),
          ),
        ),
      );

  /// Pins the delivery point on the real map and resolves a street address.
  Future<void> _pin(LatLng p) async {
    app.setDeliveryPoint(p.latitude, p.longitude);
    setState(() {});
    final label = await location.describe(p.latitude, p.longitude);
    if (label == null || !mounted) return;
    app.setDeliveryPoint(p.latitude, p.longitude, address: label);
    setState(() {});
  }

  Future<void> _useMyGps() async {
    final fix = await location.current();
    if (!mounted) return;
    if (fix == null) {
      toast(context, 'Location is unavailable. Turn on GPS or pick a pin on the map.');
      return;
    }
    app.setGeo(fix.lat, fix.lng, label: fix.label);
    app.setDeliveryPoint(fix.lat, fix.lng, address: fix.label);
    setState(() {});
  }

  Widget _map(BuildContext context) => LiveMap(
        height: 265,
        destination: app.deliveryPoint ?? app.geoPoint ?? MapConfig.kampala,
        radius: 18,
        myLocation: app.locationOn,
        showRoute: false,
        showRecenter: false,
        padding: const EdgeInsets.only(bottom: 90),
        onTap: _pin,
        overlay: Positioned(top: 12, right: 12, child: RoundAction(IconName.location, onTap: _useMyGps)),
        footer: Tap(
          onTap: () async {
            await showAddressSheet(context);
            if (mounted) setState(() {});
          },
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 11),
            decoration: BoxDecoration(color: const Color(0xEB0C0E11), borderRadius: BorderRadius.circular(12), border: Border.all(color: FC.line)),
            child: Row(children: [
              Ic(IconName.location, size: 17, color: FC.gold),
              const SizedBox(width: 12),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  FcText('DELIVERY LOCATION · TAP MAP TO MOVE PIN', kind: Tx.caption, color: FC.muted),
                  FcText(app.deliveryAddress, kind: Tx.label, maxLines: 1),
                ]),
              ),
              Ic(IconName.chevron, size: 16, color: FC.muted),
            ]),
          ),
        ),
      );

  @override
  Widget build(BuildContext context) {
    final nowSel = !app.scheduled;
    final sched = app.scheduledAt == null ? 'Choose a time' : 'Today, ${MaterialLocalizations.of(context).formatTimeOfDay(app.scheduledAt!)}';
    return AppPage(
      header: PageHeader(title: 'Delivery details', goBack: () => app.backOr(Screen.vehicle)),
      body: Narrow(gap: 22, children: [
        _stepIntro('STEP 3 OF 4 · DELIVERY', 'Where should we meet you?'),
        _map(context),
        const FcText('Delivery time', kind: Tx.subtitle),
        Row(children: [
          _choice(IconName.clock, 'Deliver now', '18–24 min', nowSel, () => setState(() => app.scheduled = false)),
          const SizedBox(width: 10),
          _choice(IconName.calendar, 'Schedule', sched, !nowSel, _pickTime),
        ]),
        FcField(label: 'Delivery note (optional)', hint: 'Vehicle color, parking level...', controller: _note, onChanged: (v) => app.deliveryNote = v),
        Container(
          padding: const EdgeInsets.only(top: 18),
          decoration: BoxDecoration(border: Border(top: BorderSide(color: FC.line))),
          child: Row(children: [
            ClipRRect(borderRadius: BorderRadius.circular(10), child: Image.asset('assets/images/station-hero.png', width: 48, height: 48, fit: BoxFit.cover)),
            const SizedBox(width: 12),
            Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              FcText(livePrices.selected.name, kind: Tx.label),
              FcText('${app.productName} · ${app.litres} litres', kind: Tx.caption, color: FC.muted),
            ])),
            FcText('UGX ${fmt(app.fuelTotal)}', kind: Tx.subtitle),
          ]),
        ),
        FcButton('Review payment', onTap: () => widget.go(Screen.payment)),
      ]),
    );
  }
}

// ===========================================================================
// Payment
// ===========================================================================
class PaymentScreen extends StatefulWidget {
  final Go go;
  const PaymentScreen({super.key, required this.go});
  @override
  State<PaymentScreen> createState() => _PaymentScreenState();
}

class _PaymentScreenState extends State<PaymentScreen> {
  bool _busy = false;

  Widget _icon(PayMethod m) => Container(
        width: 44,
        height: 38,
        alignment: Alignment.center,
        decoration: BoxDecoration(color: m.badgeBg ?? const Color(0xFF252930), borderRadius: BorderRadius.circular(8)),
        child: m.icon != null ? Ic(m.icon!) : Text(m.badge, style: fs(10.4, color: m.badgeFg ?? FC.ink, w: FontWeight.w800, h: 1)),
      );

  Future<void> _pay() async {
    final err = app.charge();
    if (err != null) {
      toast(context, err);
      return;
    }
    setState(() => _busy = true);
    await Future.delayed(const Duration(milliseconds: 1200));
    if (!mounted) return;
    // Local reference + demand signal; the backend returns the canonical order
    // id when `POST /orders` lands (tracking adopts it automatically).
    app.newOrderId();
    livePrices.recordOrder(livePrices.selectedId, app.fuelType == 'Diesel' ? FuelType.diesel : FuelType.petrol, app.litres.toDouble());
    setState(() => _busy = false);
    widget.go(Screen.tracking);
  }

  @override
  Widget build(BuildContext context) {
    final total = app.orderTotal;
    return AppPage(
      header: PageHeader(title: 'Payment', goBack: () => app.backOr(Screen.checkout)),
      body: Narrow(gap: 22, children: [
        _stepIntro('STEP 4 OF 4 · PAYMENT', 'Choose payment method'),
        Column(children: gapped([
          for (final m in app.payMethods)
            Tap(
              onTap: () => setState(() => app.payId = m.id),
              child: Container(
                constraints: const BoxConstraints(minHeight: 72),
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(color: app.payId == m.id ? al(FC.gold, .05) : FC.surface, borderRadius: BorderRadius.circular(12), border: Border.all(color: app.payId == m.id ? FC.gold : FC.line)),
                child: Row(children: [
                  _icon(m),
                  const SizedBox(width: 12),
                  Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    FcText(m.title, kind: Tx.label),
                    FcText(m.id == 'wallet' ? 'Balance UGX ${fmt(app.walletBalance)}' : m.caption, kind: Tx.caption, color: FC.muted),
                  ])),
                  RadioDot(selected: app.payId == m.id),
                ]),
              ),
            ),
        ], 10)),
        Align(
          alignment: Alignment.centerLeft,
          child: Tap(
            onTap: () async {
              final ok = await showAddPaySheet(context);
              if (ok == true && mounted) setState(() => app.payId = app.payMethods.last.id);
            },
            child: Padding(padding: const EdgeInsets.symmetric(vertical: 6), child: Row(mainAxisSize: MainAxisSize.min, children: [
              Ic(IconName.plus, color: FC.gold),
              const SizedBox(width: 6),
              Flexible(child: Text('Add new payment method', style: fs(11.2, color: FC.gold, w: FontWeight.w700))),
            ])),
          ),
        ),
        Panel(
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: gapped([
            const FcText('Order summary', kind: Tx.subtitle),
            KvRow('${app.productName} · ${app.litres}L', 'UGX ${fmt(app.fuelTotal)}'),
            KvRow('Delivery fee', 'UGX ${fmt(AppState.deliveryFee)}'),
            KvRow('Service fee', 'UGX ${fmt(AppState.serviceFee)}'),
            TotalRow('Total', 'UGX ${fmt(total)}'),
          ], 13)),
        ),
        Row(mainAxisAlignment: MainAxisAlignment.center, children: [
          Ic(IconName.shield, size: 16, color: FC.green),
          const SizedBox(width: 6),
          Expanded(child: FcText('Encrypted and protected payment', kind: Tx.caption, color: FC.muted, align: TextAlign.center)),
        ]),
        FcButton('Confirm & pay UGX ${fmt(total)}', loading: _busy, onTap: _pay),
      ]),
    );
  }
}

// ===========================================================================
// Live tracking
// ===========================================================================
class TrackingScreen extends StatefulWidget {
  final Go go;
  const TrackingScreen({super.key, required this.go});
  @override
  State<TrackingScreen> createState() => _TrackingScreenState();
}

class _TrackingScreenState extends State<TrackingScreen> {
  @override
  void initState() {
    super.initState();
    _begin();
  }

  /// Opens one tracking session for the order that was just paid for.
  ///
  /// [tracker] streams `GET /orders/{id}/tracking` every few seconds and falls
  /// back to a labelled preview while the backend is still being built, so the
  /// map, driver and fuel gauges are never empty.
  Future<void> _begin() async {
    final station = livePrices.selected;
    final id = app.activeOrderId ?? app.newOrderId();
    final running = tracker.order;
    if (running == null || running.orderId != id || !running.stage.active) {
      await tracker.start(OrderSeed(
        orderId: id,
        litres: app.litres,
        pickup: station.point,
        destination: app.deliveryPoint ?? app.geoPoint ?? MapConfig.kampala,
        stationName: station.name,
        product: app.productName,
      ));
    }
    // Keep the delivery pin honest even if the customer moved after ordering.
    final fix = await location.current();
    if (fix != null && mounted) app.setGeo(fix.lat, fix.lng, label: fix.label);
  }

  Future<void> _confirm() async {
    await tracker.confirmDelivery();
    app.completeDelivery();
    haptic(HapticFeedbackType.heavy);
    if (!mounted) return;
    widget.go(Screen.success, replace: true);
  }

  Future<void> _call(Driver d) async {
    var ok = false;
    try {
      ok = await launchUrl(Uri(scheme: 'tel', path: d.phone));
    } catch (_) {
      ok = false;
    }
    if (ok || !mounted) return;
    toast(context, 'Could not open the dialler for ${d.name}.');
  }

  static String _ago(DateTime at) {
    final s = DateTime.now().difference(at).inSeconds;
    if (s < 5) return 'just now';
    if (s < 60) return '${s}s ago';
    return '${s ~/ 60}m ago';
  }

  // ------------------------------------------------------------------- map
  Widget _map(BuildContext context, OrderTracking t) => LiveMap(
        driver: t.driverPoint,
        pickup: t.pickup,
        destination: t.destination,
        route: t.route,
        myLocation: app.locationOn,
        radius: 0,
        padding: const EdgeInsets.only(top: 104, bottom: 96),
        overlay: Positioned(
          top: topInset(context) + 10,
          left: 14,
          right: 14,
          child: Row(children: [
            FcButton.icon(IconName.arrow, key: const ValueKey('page-back'), onTap: () => widget.go(Screen.home, root: true)),
            const Spacer(),
            _liveChip(t),
          ]),
        ),
        footer: _mapFooter(t),
      );

  Widget _liveChip(OrderTracking t) {
    final live = tracker.isLive;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 7),
      decoration: BoxDecoration(color: al(FC.black, .84), borderRadius: BorderRadius.circular(20), border: Border.all(color: FC.line)),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        PulseDot(color: live ? FC.green : FC.gold, size: 5),
        const SizedBox(width: 7),
        Text(live ? 'LIVE' : 'PREVIEW', style: fs(8.8, color: live ? FC.green : FC.gold, w: FontWeight.w800, ls: .8, h: 1)),
        const SizedBox(width: 8),
        Text('#${t.orderId}', style: fs(9.6, color: FC.muted, h: 1)),
      ]),
    );
  }

  Widget _mapFooter(OrderTracking t) {
    final remaining = (t.driverPoint != null && t.destination != null) ? distanceKm(t.driverPoint!, t.destination!) : null;
    final away = remaining == null
        ? 'Locating your partner'
        : remaining < 1
            ? '${(remaining * 1000).round()} m away'
            : '${remaining.toStringAsFixed(1)} km away';
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 11),
      decoration: BoxDecoration(color: al(FC.black, .88), borderRadius: BorderRadius.circular(12), border: Border.all(color: FC.line)),
      child: Row(children: [
        Ic(IconName.truck, size: 16, color: FC.gold),
        const SizedBox(width: 10),
        Expanded(
          child: FcText('$away · updated ${_ago(t.updatedAt)}', kind: Tx.caption, color: FC.muted, maxLines: 1),
        ),
        const SizedBox(width: 8),
        Text('${(t.routeProgress * 100).round()}%', style: fs(9.6, color: FC.gold, w: FontWeight.w800, h: 1)),
      ]),
    );
  }

  // --------------------------------------------------------------- sheet
  Widget _sheet(BuildContext context, OrderTracking t, {required bool handle}) {
    final done = t.stage == OrderStage.delivered || t.stage == OrderStage.cancelled;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: gapped([
        if (handle)
          Center(child: Container(width: 42, height: 4, decoration: BoxDecoration(color: FC.line, borderRadius: BorderRadius.circular(4)))),
        Entrance(_headline(t), index: 0),
        Entrance(_driverCard(context, t), index: 1),
        Entrance(_fuelCard(t), index: 2),
        Entrance(_timeline(t), index: 3),
        if (tracker.error != null) Entrance(FcText(tracker.error!, kind: Tx.caption, color: FC.danger), index: 4),
        Entrance(
          Column(children: gapped([
            if (done)
              FcButton('Back to home', onTap: () => widget.go(Screen.home, root: true))
            else if (t.stage == OrderStage.arriving)
              FcButton('Confirm delivery', onTap: _confirm)
            else
              FcButton('Cancel order', variant: BV.ghost, onTap: () => widget.go(Screen.cancelOrder)),
            FcText('UGX ${fmt(app.orderTotal)} · ${app.productName} ${app.litres}L', kind: Tx.caption, color: FC.muted, align: TextAlign.center),
          ], 10)),
          index: 5,
        ),
      ], 16),
    );
  }

  Widget _headline(OrderTracking t) => Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            FcText(t.stage.headline, kind: Tx.title),
            const SizedBox(height: 6),
            AnimatedSwitcher(
              duration: Motion.base,
              child: FcText(_stageHint(t), key: ValueKey(t.stage), kind: Tx.caption, color: FC.muted),
            ),
          ]),
        ),
        const SizedBox(width: 12),
        _etaRing(t),
      ]);

  String _stageHint(OrderTracking t) => switch (t.stage) {
        OrderStage.confirmed => 'We are matching you with a certified partner.',
        OrderStage.collecting => 'Metering ${t.litres}L into sealed delivery containers.',
        OrderStage.enRoute => 'Following your partner live on the map.',
        OrderStage.arriving => 'Meet your partner at your vehicle.',
        OrderStage.delivered => 'Fuel dispensed and payment complete.',
        OrderStage.cancelled => 'This delivery was cancelled.',
      };

  Widget _etaRing(OrderTracking t) {
    final done = t.stage == OrderStage.delivered || t.stage == OrderStage.cancelled;
    return Container(
      width: 74,
      height: 74,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: al(FC.gold, .05),
        border: Border.all(color: al(FC.gold, .30)),
      ),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: done
            ? [Ic(IconName.check, size: 24, color: FC.gold)]
            : [
                AnimatedSwitcher(
                  duration: Motion.fast,
                  child: Text('${t.etaMinutes}', key: ValueKey(t.etaMinutes), style: fs(23.2, color: FC.gold, w: FontWeight.w700, h: 1)),
                ),
                Text('MIN', style: fs(7.68, color: FC.gold, w: FontWeight.w800, h: 1.3)),
              ],
      ),
    );
  }

  Widget _driverCard(BuildContext context, OrderTracking t) {
    final d = t.driver;
    if (d == null) {
      return Panel(
        radius: 14,
        padding: const EdgeInsets.all(13),
        child: Row(children: [
          PulseDot(color: FC.gold, size: 5),
          const SizedBox(width: 10),
          Expanded(child: FcText('Matching a certified delivery partner…', kind: Tx.caption, color: FC.muted)),
        ]),
      );
    }
    return Panel(
      radius: 14,
      padding: const EdgeInsets.all(12),
      child: Row(children: [
        Container(
          width: 46,
          height: 46,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: al(FC.gold, .12),
            border: Border.all(color: al(FC.gold, .45)),
          ),
          child: Text(d.initials, style: fs(13, color: FC.gold, w: FontWeight.w800, h: 1)),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            FcText(d.name, kind: Tx.label),
            const SizedBox(height: 2),
            FcText(d.caption.isEmpty ? 'Certified delivery partner' : d.caption, kind: Tx.caption, color: FC.muted, maxLines: 1),
          ]),
        ),
        FcButton.icon(IconName.phone, onTap: d.phone.isEmpty ? null : () => _call(d)),
      ]),
    );
  }

  Widget _fuelCard(OrderTracking t) => Panel(
        radius: 14,
        padding: const EdgeInsets.all(14),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Row(children: [
            Ic(IconName.fuel, size: 16, color: FC.gold),
            const SizedBox(width: 8),
            const FcText('Fuel on board', kind: Tx.label),
            const Spacer(),
            FcText('${fmt((t.deliveredFraction * 100).round())}%', kind: Tx.caption, color: FC.gold),
          ]),
          const SizedBox(height: 10),
          AnimatedProgress(t.deliveredFraction, height: 7),
          const SizedBox(height: 12),
          Row(children: [
            _fuelStat('Loaded', '${t.litresLoaded.round()} L'),
            const SizedBox(width: 20),
            _fuelStat('In your tank', '${t.litresDispensed.round()} L'),
            const SizedBox(width: 20),
            _fuelStat('Ordered', '${t.litres} L'),
          ]),
        ]),
      );

  Widget _fuelStat(String label, String value) => Expanded(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(value, style: fs(13.6, w: FontWeight.w700, h: 1.2)),
          Text(label, style: fs(9.28, color: FC.muted, h: 1.3)),
        ]),
      );

  Widget _timeline(OrderTracking t) {
    const stages = [OrderStage.confirmed, OrderStage.collecting, OrderStage.enRoute, OrderStage.arriving];
    final done = t.stage == OrderStage.delivered;
    return Column(children: [
      for (var i = 0; i < stages.length; i++)
        _timelineItem(stages[i].label, i, done ? stages.length : t.stage.step, done, i == stages.length - 1),
    ]);
  }

  Widget _timelineItem(String label, int i, int current, bool complete, bool last) {
    final reached = complete || i <= current;
    final checked = complete || i < current;
    return SizedBox(
      height: 36,
      child: Stack(children: [
        if (!last)
          Positioned(
            left: 10,
            top: 21,
            child: AnimatedContainer(
              duration: Motion.base,
              width: 1.5,
              height: 20,
              color: checked ? al(FC.gold, .55) : FC.line,
            ),
          ),
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          SizedBox(
            width: 28,
            child: Align(
              alignment: Alignment.topLeft,
              child: AnimatedContainer(
                duration: Motion.base,
                curve: Motion.soft,
                width: 21,
                height: 21,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: checked ? FC.gold : (reached ? al(FC.gold, .18) : null),
                  border: Border.all(color: reached ? FC.gold : FC.dim),
                ),
                child: checked
                    ? const Ic(IconName.check, size: 12, color: Color(0xFF111111))
                    : Text('${i + 1}', style: fs(8.8, color: reached ? FC.gold : FC.dim, h: 1)),
              ),
            ),
          ),
          const SizedBox(width: 9),
          Padding(
            padding: const EdgeInsets.only(top: 3),
            child: FcText(label, kind: Tx.label, color: reached ? FC.ink : FC.dim),
          ),
        ]),
      ]),
    );
  }

  // -------------------------------------------------------------- layout
  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: FC.black,
      child: ListenableBuilder(
        listenable: tracker,
        builder: (context, _) {
          final t = tracker.order;
          if (t == null) {
            return Center(child: CircularProgressIndicator(color: FC.gold));
          }
          return _layout(context, t);
        },
      ),
    );
  }

  Widget _layout(BuildContext context, OrderTracking t) {
    final pad = cl(context, 20, 6, 54);
    if (isWide(context)) {
      return Row(children: [
        Expanded(flex: 56, child: _map(context, t)),
        Expanded(
          flex: 44,
          child: LayoutBuilder(
            builder: (c, cons) => SingleChildScrollView(
              child: ConstrainedBox(
                constraints: BoxConstraints(minHeight: cons.maxHeight),
                child: Center(
                  child: Padding(
                    padding: EdgeInsets.symmetric(horizontal: vw(context) * .05, vertical: vh(context) * .06),
                    child: _sheet(context, t, handle: false),
                  ),
                ),
              ),
            ),
          ),
        ),
      ]);
    }

    // Phone: the map stays fixed and interactive, the details scroll under it.
    final sheetH = math.max(vh(context) * .54, 340.0);
    return Stack(children: [
      Positioned(left: 0, right: 0, top: 0, bottom: sheetH - 24, child: _map(context, t)),
      Positioned(
        left: 0,
        right: 0,
        bottom: 0,
        height: sheetH,
        child: Container(
          decoration: BoxDecoration(
            color: FC.black,
            borderRadius: const BorderRadius.vertical(top: Radius.circular(28)),
            border: Border(top: BorderSide(color: FC.line)),
          ),
          child: SingleChildScrollView(
            padding: EdgeInsets.fromLTRB(pad, 14, pad, 28 + bottomInset(context)),
            child: _sheet(context, t, handle: true),
          ),
        ),
      ),
    ]);
  }
}

// ===========================================================================
// Delivery complete
// ===========================================================================
class SuccessScreen extends StatefulWidget {
  final Go go;
  const SuccessScreen({super.key, required this.go});
  @override
  State<SuccessScreen> createState() => _SuccessScreenState();
}

class _SuccessScreenState extends State<SuccessScreen> {
  int _rating = 5;

  @override
  Widget build(BuildContext context) {
    final pad = cl(context, 22, 6, 50);
    return ColoredBox(
      color: FC.black,
      child: Stack(children: [
        const Positioned.fill(child: Glow(fx: .5, fy: .18, colors: [Color(0x14F5C72E), Color(0x00F5C72E)], stops: [0, .30])),
        SingleChildScrollView(
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 560),
              child: Padding(
                padding: EdgeInsets.fromLTRB(pad, vh(context) * .09 + topInset(context), pad, 40 + bottomInset(context)),
                child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: gapped([
                  Center(
                    child: Container(
                      width: 132,
                      height: 132,
                      margin: const EdgeInsets.only(bottom: 10),
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        border: Border.all(color: al(FC.gold, .13)),
                        boxShadow: [BoxShadow(color: al(FC.gold, .025), spreadRadius: 18), BoxShadow(color: al(FC.gold, .015), spreadRadius: 36)],
                      ),
                      child: Center(
                        child: Container(
                          width: 82,
                          height: 82,
                          decoration: BoxDecoration(shape: BoxShape.circle, color: FC.gold, boxShadow: [BoxShadow(color: al(FC.gold, .18), blurRadius: 45, offset: const Offset(0, 14))]),
                          child: const Center(child: Ic(IconName.check, size: 44, color: Color(0xFF111111))),
                        ),
                      ),
                    ),
                  ),
                  const FcText('Delivery complete.', kind: Tx.display, align: TextAlign.center),
                  FcText('${app.litres} litres of ${app.productName.toLowerCase()} were delivered safely to your location.', color: FC.muted, align: TextAlign.center),
                  Panel(
                    padding: const EdgeInsets.all(16),
                    child: Column(children: gapped([
                      KvRow('Order ID', app.orderIdLabel, size: 10.88),
                      KvRow('Total paid', 'UGX ${fmt(app.orderTotal)}', size: 10.88),
                      KvRow('Payment', app.selectedPay.title, size: 10.88),
                    ], 11)),
                  ),
                  const FcText('How was your delivery?', kind: Tx.subtitle, align: TextAlign.center),
                  Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                    for (var s = 1; s <= 5; s++)
                      Tap(
                        onTap: () => setState(() => _rating = s),
                        child: Padding(padding: EdgeInsets.only(left: s == 1 ? 0 : 9), child: Ic(IconName.star, size: 26, color: FC.gold, filled: s <= _rating)),
                      ),
                  ]),
                  FcButton('Back to home', key: const ValueKey('page-back'), onTap: () => widget.go(Screen.home, root: true)),
                  FcButton('View receipt', variant: BV.ghost, onTap: () => widget.go(Screen.orders, root: true)),
                ], 19)),
              ),
            ),
          ),
        ),
      ]),
    );
  }
}

// ===========================================================================
// Cancel order (NEW)
// ===========================================================================
class CancelOrderScreen extends StatefulWidget {
  final Go go;
  const CancelOrderScreen({super.key, required this.go});
  @override
  State<CancelOrderScreen> createState() => _CancelOrderScreenState();
}

class _CancelOrderScreenState extends State<CancelOrderScreen> {
  static const int _cancelFee = 8000;
  static const _reasons = [
    'Delivery is taking too long',
    'I changed my mind',
    'Incorrect delivery location',
    'Ordered the wrong fuel or quantity',
    'Other reason',
  ];

  String _reason = '';
  bool _cancelled = false;

  @override
  Widget build(BuildContext context) => _cancelled ? _done(context) : _form(context);

  // ---------------------------------------------------------------- form
  Widget _form(BuildContext context) {
    final paid = app.orderTotal;
    final refund = paid - _cancelFee;
    return AppPage(
      header: PageHeader(title: 'Cancel order', goBack: () => widget.go(Screen.tracking)),
      body: Narrow(gap: 20, children: [
        // order summary
        Panel(
          padding: const EdgeInsets.all(14),
          child: Row(children: [
            Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(shape: BoxShape.circle, color: al(FC.gold, .08), border: Border.all(color: FC.gold)),
              child: Center(child: Ic(IconName.truck, color: FC.gold)),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const LivePill('ON THE WAY'),
                const SizedBox(height: 6),
                FcText('${app.productName} · ${app.litres}L', kind: Tx.subtitle),
                FcText('${livePrices.selected.name} · Order ${app.orderIdLabel}', kind: Tx.caption, color: FC.muted),
              ]),
            ),
            FcText('12–16 min', kind: Tx.label, color: FC.gold),
          ]),
        ),

        // intro
        Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          FcText('CANCEL DELIVERY', kind: Tx.label, color: FC.gold),
          SizedBox(height: 9),
          FcText('Why are you cancelling?', kind: Tx.title),
          SizedBox(height: 9),
          FcText('Your feedback helps us improve the FuelOnDemand experience.', color: FC.muted),
        ]),

        // reasons
        Column(
          children: gapped([
            for (final r in _reasons)
              Tap(
                onTap: () => setState(() => _reason = r),
                child: Container(
                  constraints: const BoxConstraints(minHeight: 56),
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                  decoration: BoxDecoration(
                    color: _reason == r ? al(FC.gold, .06) : FC.surface,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: _reason == r ? FC.gold : FC.line),
                  ),
                  child: Row(children: [
                    RadioDot(selected: _reason == r),
                    const SizedBox(width: 12),
                    Expanded(child: FcText(r, kind: Tx.label, color: _reason == r ? FC.gold : FC.ink)),
                  ]),
                ),
              ),
          ], 10),
        ),

        // fee warning
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(color: al(FC.danger, .06), borderRadius: BorderRadius.circular(12), border: Border.all(color: al(FC.danger, .25))),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Ic(IconName.shield, color: FC.danger),
            const SizedBox(width: 12),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                FcText('Your fuel has already been collected', kind: Tx.label, color: FC.danger),
                const SizedBox(height: 3),
                FcText(
                  'A UGX ${fmt(_cancelFee)} cancellation fee applies because your delivery partner has collected the fuel and started the trip.',
                  kind: Tx.caption,
                  color: FC.muted,
                ),
              ]),
            ),
          ]),
        ),

        // refund summary
        Panel(
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: gapped([
            const FcText('Refund summary', kind: Tx.subtitle),
            KvRow('Amount paid', 'UGX ${fmt(paid)}'),
            KvRow('Cancellation fee', '− UGX ${fmt(_cancelFee)}'),
            TotalRow('You’ll receive', 'UGX ${fmt(refund)}'),
            FcText('Refunded to ${app.selectedPay.title} within 24 hours.', kind: Tx.caption, color: FC.muted),
          ], 13)),
        ),

        FcButton('Confirm cancellation', onTap: _reason.isEmpty
            ? null
            : () {
                tracker.cancel();
                setState(() => _cancelled = true);
              }),
        FcButton('Keep my order', variant: BV.outline, onTap: () => widget.go(Screen.tracking)),
        Center(
          child: TextAction(
            'Need help instead? Contact support',
            onTap: () => showSupportChat(context, topic: 'I need help with cancelling order #${app.orderIdLabel}.'),
          ),
        ),
      ]),
    );
  }

  // ---------------------------------------------------------- cancelled
  Widget _done(BuildContext context) {
    final pad = cl(context, 22, 6, 50);
    final refund = app.orderTotal - _cancelFee;
    return ColoredBox(
      color: FC.black,
      child: Stack(children: [
        const Positioned.fill(child: Glow(fx: .5, fy: .18, colors: [Color(0x14F5C72E), Color(0x00F5C72E)], stops: [0, .30])),
        SingleChildScrollView(
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 560),
              child: Padding(
                padding: EdgeInsets.fromLTRB(pad, vh(context) * .09 + topInset(context), pad, 40 + bottomInset(context)),
                child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: gapped([
                  Center(
                    child: Container(
                      width: 132,
                      height: 132,
                      margin: const EdgeInsets.only(bottom: 10),
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        border: Border.all(color: al(FC.gold, .13)),
                        boxShadow: [BoxShadow(color: al(FC.gold, .025), spreadRadius: 18), BoxShadow(color: al(FC.gold, .015), spreadRadius: 36)],
                      ),
                      child: Center(
                        child: Container(
                          width: 82,
                          height: 82,
                          decoration: BoxDecoration(shape: BoxShape.circle, color: FC.gold, boxShadow: [BoxShadow(color: al(FC.gold, .18), blurRadius: 45, offset: const Offset(0, 14))]),
                          child: const Center(child: Ic(IconName.minus, size: 40, color: Color(0xFF111111))),
                        ),
                      ),
                    ),
                  ),
                  FcText('ORDER CANCELLED', kind: Tx.label, color: FC.gold, align: TextAlign.center),
                  const FcText('Your order has been cancelled.', kind: Tx.display, align: TextAlign.center),
                  FcText(
                    'We’ve notified ${livePrices.selected.name} and your delivery partner. Your refund is being processed.',
                    color: FC.muted,
                    align: TextAlign.center,
                  ),
                  Panel(
                    padding: const EdgeInsets.all(16),
                    child: Column(children: gapped([
                      KvRow('Order ID', app.orderIdLabel, size: 10.88),
                      KvRow('Refund amount', 'UGX ${fmt(refund)}', size: 10.88),
                      KvRow('Refund method', app.selectedPay.title, size: 10.88),
                      const KvRow('Expected refund', 'Within 24 hours', size: 10.88),
                    ], 11)),
                  ),
                  Panel(
                    padding: const EdgeInsets.all(14),
                    child: Row(children: [
                      Ic(IconName.clock, color: FC.gold),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          FcText('Refund in progress', kind: Tx.label),
                          FcText('We’ll send a notification when the refund is complete.', kind: Tx.caption, color: FC.muted),
                        ]),
                      ),
                    ]),
                  ),
                  FcButton('Back to home', onTap: () => widget.go(Screen.home, root: true)),
                  FcButton('View my orders', variant: BV.ghost, onTap: () => widget.go(Screen.orders, root: true)),
                ], 19)),
              ),
            ),
          ),
        ),
      ]),
    );
  }
}