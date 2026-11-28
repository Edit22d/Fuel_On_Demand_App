import 'dart:async';
import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../core/core.dart';
import '../services/auth_service.dart';
import '../services/location_service.dart';
import 'sheets.dart';

// ===========================================================================
// Shared widgets: real logo + live station card
// ===========================================================================
class StationLogo extends StatelessWidget {
  final LiveStation s;
  final double size;
  const StationLogo(this.s, {super.key, this.size = 48});

  @override
  Widget build(BuildContext context) => Container(
        width: size,
        height: size,
        padding: EdgeInsets.all(size * .12),
        decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(size * .26), border: Border.all(color: FC.line)),
        child: s.logoAsset.isEmpty
            // No brand logo on file yet — show the brand initial instead.
            ? Center(child: Text(s.brand[0], style: fs(size * .4, color: FC.onGold, w: FontWeight.w800)))
            : Image.asset(
                s.logoAsset,
                fit: BoxFit.contain,
                // Falls back to a letter if the logo file is missing.
                errorBuilder: (_, __, ___) => Center(child: Text(s.brand[0], style: fs(size * .4, color: FC.onGold, w: FontWeight.w800))),
              ),
      );
}

String _pill(String id, FuelType f) {
  final p = livePrices.changePct(id, f);
  if (p.abs() < .005) return 'Base price';
  return '${p > 0 ? '+' : '−'}${p.abs().toStringAsFixed(2)}%';
}

class _PriceCell extends StatelessWidget {
  final String id, label;
  final FuelType fuel;
  const _PriceCell(this.id, this.label, this.fuel);

  @override
  Widget build(BuildContext context) {
    final move = livePrices.lastMove(id, fuel);
    return Expanded(
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(color: FC.surface2, borderRadius: BorderRadius.circular(12), border: Border.all(color: FC.line)),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          FcText(label, kind: Tx.caption, color: FC.muted),
          const SizedBox(height: 4),
          AnimatedSwitcher(
            duration: const Duration(milliseconds: 350),
            child: FcText('${ugx(livePrices.price(id, fuel))}/L', key: ValueKey(livePrices.price(id, fuel)), kind: Tx.subtitle, color: FC.gold),
          ),
          const SizedBox(height: 4),
          Row(children: [
            Icon(move > 0 ? Icons.arrow_upward : move < 0 ? Icons.arrow_downward : Icons.remove, size: 12, color: FC.muted),
            const SizedBox(width: 4),
            // Two price cells share a phone-width card, so the change pill has
            // to shrink instead of overflowing.
            Flexible(child: FcText(_pill(id, fuel), kind: Tx.caption, color: FC.muted, maxLines: 1)),
          ]),
        ]),
      ),
    );
  }
}

/// Card for a station with both live prices. Rebuilds whenever prices move.
class LiveStationCard extends StatelessWidget {
  final LiveStation s;
  final VoidCallback onTap;
  const LiveStationCard(this.s, {super.key, required this.onTap});

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
        animation: livePrices,
        builder: (_, __) => Tap(
          onTap: onTap,
          child: Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(color: FC.surface, borderRadius: BorderRadius.circular(16), border: Border.all(color: FC.line)),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                StationLogo(s, size: 48),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    FcText(s.name, kind: Tx.subtitle, maxLines: 1),
                    FcText('${s.km.toStringAsFixed(1)} km · ${s.etaMin}–${s.etaMax} min · ${s.reviews == 0 ? 'New station' : '★ ${s.rating}'}', kind: Tx.caption, color: FC.muted),
                  ]),
                ),
                const LivePill('Live'),
              ]),
              const SizedBox(height: 14),
              Row(children: [
                _PriceCell(s.id, 'Petrol', FuelType.petrol),
                const SizedBox(width: 10),
                _PriceCell(s.id, 'Diesel', FuelType.diesel),
              ]),
            ]),
          ),
        ),
      );
}

/// Compact live map for the home screen: your GPS pin, the closest forecourt
/// and the delivery line between them.
class NearbyMapCard extends StatefulWidget {
  final Go go;
  const NearbyMapCard({super.key, required this.go});

  @override
  State<NearbyMapCard> createState() => _NearbyMapCardState();
}

class _NearbyMapCardState extends State<NearbyMapCard> {
  Future<void> _locate() async {
    final fix = await location.current();
    if (!mounted) return;
    if (fix == null) {
      toast(context, 'Location is unavailable on this device.');
      return;
    }
    app.setGeo(fix.lat, fix.lng, label: fix.label);
    app.setDeliveryPoint(fix.lat, fix.lng, address: fix.label);
    setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final me = app.geoPoint;
    final near = stationNetwork.all.reduce((a, b) => a.km <= b.km ? a : b);
    return LiveMap(
      height: 200,
      center: me ?? near.point,
      destination: me,
      pickup: near.point,
      route: me == null ? const [] : [near.point, me],
      showRecenter: false,
      radius: 16,
      overlay: Stack(children: [
        Positioned(
          left: 12,
          top: 12,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
            decoration: BoxDecoration(color: al(FC.black, .82), borderRadius: BorderRadius.circular(20), border: Border.all(color: FC.line)),
            child: Row(mainAxisSize: MainAxisSize.min, children: [
              PulseDot(color: FC.gold, size: 4),
              const SizedBox(width: 6),
              Text('NEAREST · ${near.name.toUpperCase()}', style: fs(8.2, color: FC.gold, w: FontWeight.w800, ls: .7, h: 1.2)),
            ]),
          ),
        ),
        Positioned(top: 12, right: 12, child: RoundAction(IconName.location, onTap: _locate)),
      ]),
      footer: Tap(
        onTap: () => _open(widget.go, near),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          decoration: BoxDecoration(color: al(FC.black, .88), borderRadius: BorderRadius.circular(12), border: Border.all(color: FC.line)),
          child: Row(children: [
            Ic(IconName.fuel, size: 16, color: FC.gold),
            const SizedBox(width: 10),
            Expanded(child: FcText('${near.name} · ${near.km} km · ${near.etaMin}–${near.etaMax} min', kind: Tx.caption, color: FC.ink, maxLines: 1)),
            Ic(IconName.chevron, size: 15, color: FC.muted),
          ]),
        ),
      ),
    );
  }
}

List<LiveStation> _stations(String query) {
  final q = query.trim().toLowerCase();
  if (q.isEmpty) return stationNetwork.all;
  return stationNetwork.all.where((s) {
    final hay = '${s.name} ${s.brand} petrol diesel'.toLowerCase();
    return q.split(RegExp(r'\s+')).every(hay.contains);
  }).toList();
}

void _open(Go go, LiveStation s) {
  livePrices.selectedId = s.id;
  go(Screen.station);
}

// ===========================================================================
// Home
// ===========================================================================
class HomeScreen extends StatefulWidget {
  final Go go;
  const HomeScreen({super.key, required this.go});
  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final _q = TextEditingController();
  String _query = '';

  @override
  void dispose() {
    _q.dispose();
    super.dispose();
  }

  /// The only destinations surfaced in the home menu.
  static const _menu = [
    (IconName.home, 'Home', Screen.home),
    (IconName.fuel, 'Stations available', Screen.partners),
    (IconName.card, 'Payments', Screen.wallet),
    (IconName.bell, 'Notifications', Screen.notifications),
    (IconName.settings, 'Settings', Screen.appSettings),
    (IconName.profile, 'Account', Screen.profile),
  ];

  Future<void> _openMenu(BuildContext context) async {
    final target = await showFcSheet<Screen>(
      context,
      title: 'Menu',
      builder: (ctx) => Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        for (final (icon, label, screen) in _menu)
          Tap(
            onTap: () => Navigator.of(ctx).pop(screen),
            child: Container(
              constraints: const BoxConstraints(minHeight: 54),
              decoration: BoxDecoration(border: screen == _menu.last.$3 ? null : Border(bottom: BorderSide(color: FC.line))),
              child: Row(children: [
                Ic(icon, color: FC.gold),
                const SizedBox(width: 14),
                Expanded(child: FcText(label, kind: Tx.label)),
                Ic(IconName.chevron, size: 18, color: FC.dim),
              ]),
            ),
          ),
      ]),
    );
    if (target == null || !mounted) return;
    // Home and Stations are roots of the customer navigation; everything else
    // pushes on top so back returns to the home screen.
    widget.go(target, root: target == Screen.home || target == Screen.partners);
  }

  Future<void> _addStation() async {
    final added = await showAddStationSheet(context);
    if (!mounted || added != true) return;
    setState(() {});
    toast(context, 'Station added to your network.', gold: true);
  }

  Widget _quick(BuildContext context, IconName icon, String label, Widget value, String pill) => LayoutBuilder(
        builder: (context, cons) {
          // Two of these sit side by side on a phone, and system text can grow:
          // once the card gets narrow the badge drops under the value instead of
          // squeezing it into an overflow.
          final stacked = cons.maxWidth < 210;
          final badge = LivePill(pill);
          return Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              gradient: const LinearGradient(begin: Alignment.topLeft, end: Alignment.bottomRight, colors: [Color(0xFF15181C), Color(0xFF0E1114)]),
              borderRadius: BorderRadius.circular(18),
              border: Border.all(color: FC.line),
            ),
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(color: al(FC.gold, .09), borderRadius: BorderRadius.circular(10)),
                child: Ic(icon, color: FC.gold),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  FcText(label, kind: Tx.label, color: FC.muted),
                  value,
                  if (stacked) Padding(padding: const EdgeInsets.only(top: 6), child: badge),
                ]),
              ),
              if (!stacked) ...[const SizedBox(width: 8), badge],
            ]),
          );
        },
      );

  /// Standard 44px hamburger action that sits in the top-right corner next to
  /// the avatar, with a matching rounded-square frame and a readable hit area.
  Widget _menuButton(BuildContext context) => Semantics(
        button: true,
        label: 'Open menu',
        child: Tap(
          onTap: () => _openMenu(context),
          child: Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              color: const Color(0xB8080A0C),
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: al(Colors.white, .14)),
            ),
            child: Center(child: Ic(IconName.menu, size: 21)),
          ),
        ),
      );

  @override
  Widget build(BuildContext context) {
    final wide = isWide(context);
    final pad = cl(context, 20, 5, 70);
    final results = _stations(_query);
    final hero = ConstrainedBox(
      constraints: BoxConstraints(minHeight: wide ? 485 : 395),
      child: Stack(children: [
        Positioned.fill(child: Image.asset('assets/images/station-hero.png', fit: BoxFit.cover, alignment: const Alignment(0, .14))),
        const Positioned.fill(
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(colors: [Color(0xF8080A0C), Color(0xAD080A0C), Color(0x66080A0C)], stops: [0, .62, 1]),
            ),
          ),
        ),
        Positioned.fill(
          child: DecoratedBox(
            decoration: BoxDecoration(gradient: LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter, colors: [Color(0x00080A0C), FC.black], stops: [.55, 1])),
          ),
        ),
        Padding(
          padding: EdgeInsets.fromLTRB(pad, topInset(context) + 26, math.max(pad, kRightInset), 30),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  FcText('Good evening,', kind: Tx.caption, color: FC.muted),
                  FcText(auth.profile.name, kind: Tx.subtitle, maxLines: 1),
                ]),
              ),
              const SizedBox(width: 12),
              Tap(
                onTap: () => widget.go(Screen.profile),
                child: Container(
                  width: 44,
                  height: 44,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(shape: BoxShape.circle, color: FC.surface2, border: Border.all(color: const Color(0xFF6B5A1E))),
                  child: Text(auth.profile.initials, style: fs(11.2, color: FC.gold, w: FontWeight.w800, h: 1)),
                ),
              ),
              const SizedBox(width: 10),
              _menuButton(context),
            ]),
            const SizedBox(height: 20),
            Tap(
              onTap: () async {
                await showLocationSheet(context);
                if (mounted) setState(() {});
              },
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                decoration: BoxDecoration(color: const Color(0xB8080A0C), borderRadius: BorderRadius.circular(20), border: Border.all(color: al(Colors.white, .1))),
                child: Row(mainAxisSize: MainAxisSize.min, children: [
                  Ic(IconName.location, size: 16, color: FC.gold),
                  const SizedBox(width: 8),
                  Text(app.location, style: fs(10.56)),
                  const SizedBox(width: 8),
                  Ic(IconName.chevron, size: 15, color: FC.muted),
                ]),
              ),
            ),
            const SizedBox(height: 42),
            ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 570),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: gapped([
                FcText('FUEL ON YOUR SCHEDULE', kind: Tx.label, color: FC.gold),
                const FcText('Running low?\nWe’re already close.', kind: Tx.display),
                FcText('Genuine fuel from Stabex and Shell, delivered safely to you.', color: FC.muted),
                const SizedBox(height: 0),
                FcButton('Order fuel now', expand: false, trailingIcon: IconName.arrow, onTap: () => _open(widget.go, stationNetwork.all.first)),
              ], 13)),
            ),
          ]),
        ),
      ]),
    );

    final quick = LayoutBuilder(builder: (c, cons) {
      final one = vw(context) <= 380;
      final a = AnimatedBuilder(
        animation: livePrices,
        builder: (_, __) {
          final avg = livePrices.petrolAverage;
          final base = stationNetwork.all.map((s) => s.basePrice[FuelType.petrol]!).reduce((a, b) => a + b) / stationNetwork.all.length;
          final p = (avg - base) / base * 100;
          return _quick(
            context,
            IconName.fuel,
            'Petrol average',
            Text.rich(TextSpan(style: ts(context, Tx.subtitle), children: [TextSpan(text: '${ugx(avg)} '), TextSpan(text: '/L', style: fs(10.4, color: FC.muted))])),
            p.abs() < .05 ? 'Stable' : '${p > 0 ? '+' : '−'}${p.abs().toStringAsFixed(1)}%',
          );
        },
      );
      final avgEta = stationNetwork.all.map((s) => (s.etaMin + s.etaMax) / 2).reduce((a, b) => a + b) / stationNetwork.all.length;
      final b = _quick(context, IconName.clock, 'Avg. arrival', Text.rich(TextSpan(style: ts(context, Tx.subtitle), children: [TextSpan(text: '${avgEta.round()} '), TextSpan(text: 'min', style: fs(10.4, color: FC.muted))])), 'Live');
      if (one) return Column(children: [a, const SizedBox(height: 12), b]);
      return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [Expanded(child: a), const SizedBox(width: 12), Expanded(child: b)]);
    });

    final list = results.isEmpty
        ? Padding(padding: const EdgeInsets.symmetric(vertical: 24), child: FcText('No stations match your search.', color: FC.muted, align: TextAlign.center))
        : LayoutBuilder(builder: (c, cons) {
            final cols = wide ? 2 : 1;
            final w = (cons.maxWidth - 14 * (cols - 1)) / cols;
            return Wrap(spacing: 14, runSpacing: 14, children: [for (final s in results) SizedBox(width: w, child: LiveStationCard(s, onTap: () => _open(widget.go, s)))]);
          });

    return AppPage(
      nav: true,
      navCurrent: Screen.home,
      go: widget.go,
      body: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        hero,
        ContentSection(children: [
          SearchBox(hint: 'Search Stabex, Shell or fuel type', controller: _q, onChanged: (v) => setState(() => _query = v)),
          const SizedBox(height: 22),
          quick,
          const SizedBox(height: 8),
          const SectionHeading('Near you', caption: 'Live map of the closest forecourt'),
          NearbyMapCard(go: widget.go),
          const SizedBox(height: 8),
          const SectionHeading('Our stations', caption: 'Live prices · update as orders come in'),
          list,
          const SizedBox(height: 16),
          FcButton('Add a station', variant: BV.outline, icon: IconName.plus, onTap: _addStation),
          const SizedBox(height: 6),
          FcText('Own a forecourt? Add it now — new stations appear here immediately.', kind: Tx.caption, color: FC.muted, align: TextAlign.center),
        ]),
      ]),
    );
  }
}

// ===========================================================================
// Partner stations
// ===========================================================================
class PartnersScreen extends StatefulWidget {
  final Go go;
  const PartnersScreen({super.key, required this.go});
  @override
  State<PartnersScreen> createState() => _PartnersScreenState();
}

class _PartnersScreenState extends State<PartnersScreen> {
  final _q = TextEditingController();
  String _query = '';
  String _filter = 'All';
  static const _filters = ['All', 'Nearest', 'Best price'];

  @override
  void dispose() {
    _q.dispose();
    super.dispose();
  }

  List<LiveStation> get _results {
    final l = _stations(_query).toList();
    if (_filter == 'Nearest') l.sort((a, b) => a.km.compareTo(b.km));
    if (_filter == 'Best price') l.sort((a, b) => livePrices.price(a.id, FuelType.petrol).compareTo(livePrices.price(b.id, FuelType.petrol)));
    return l;
  }

  @override
  Widget build(BuildContext context) {
    final wide = isWide(context);
    return AppPage(
      nav: true,
      navCurrent: Screen.partners,
      go: widget.go,
      header: PageHeader(title: 'Partner stations', goBack: () => app.backOr(Screen.home), action: RoundAction(IconName.profile, onTap: () => widget.go(Screen.profile))),
      body: ContentSection(maxWide: 2000, children: [
        Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          FcText('VERIFIED NETWORK', kind: Tx.label, color: FC.gold),
          const SizedBox(height: 8),
          ConstrainedBox(constraints: const BoxConstraints(maxWidth: 620), child: const FcText('Choose a station you trust.', kind: Tx.title)),
          const SizedBox(height: 8),
          ConstrainedBox(constraints: const BoxConstraints(maxWidth: 620), child: FcText('Compare live prices and delivery times across Kampala.', color: FC.muted)),
        ]),
        const SizedBox(height: 18),
        SearchBox(hint: 'Search by station or fuel', controller: _q, onChanged: (v) => setState(() => _query = v)),
        const SizedBox(height: 18),
        SizedBox(
          height: 34,
          child: ListView(scrollDirection: Axis.horizontal, children: [
            for (final f in _filters)
              Padding(
                padding: const EdgeInsets.only(right: 8),
                child: Tap(
                  onTap: () => setState(() => _filter = f),
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 13),
                    alignment: Alignment.center,
                    decoration: BoxDecoration(
                      color: f == _filter ? FC.gold : FC.surface,
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(color: f == _filter ? FC.gold : FC.line),
                    ),
                    child: Text(f, style: fs(9.92, color: f == _filter ? FC.onGold : FC.muted, w: f == _filter ? FontWeight.w800 : FontWeight.w400, h: 1.2)),
                  ),
                ),
              ),
          ]),
        ),
        const SectionHeading('Available near you', caption: 'Prices update live as orders are placed'),
        Builder(builder: (_) {
          final results = _results;
          if (results.isEmpty) {
            return Padding(padding: const EdgeInsets.symmetric(vertical: 24), child: FcText('No stations match your search.', color: FC.muted, align: TextAlign.center));
          }
          return LayoutBuilder(builder: (c, cons) {
            final cols = wide ? 2 : 1;
            final w = (cons.maxWidth - 14 * (cols - 1)) / cols;
            return Wrap(spacing: 14, runSpacing: 14, children: [for (final s in results) SizedBox(width: w, child: LiveStationCard(s, onTap: () => _open(widget.go, s)))]);
          });
        }),
      ]),
    );
  }
}

// ===========================================================================
// Station detail
// ===========================================================================
class StationScreen extends StatefulWidget {
  final Go go;
  const StationScreen({super.key, required this.go});
  @override
  State<StationScreen> createState() => _StationScreenState();
}

class _StationScreenState extends State<StationScreen> {
  Widget _stat(IconName icon, String value, String label, {bool last = false}) => Expanded(
        child: Container(
          decoration: BoxDecoration(border: last ? null : Border(right: BorderSide(color: FC.line))),
          child: Column(children: [
            Ic(icon, color: FC.gold),
            const SizedBox(height: 4),
            FcText(value, kind: Tx.subtitle),
            const SizedBox(height: 4),
            FcText(label, kind: Tx.caption, color: FC.muted),
          ]),
        ),
      );

  Widget _product(LiveStation s, String name, String sub, FuelType f) => Container(
        padding: const EdgeInsets.all(15),
        decoration: BoxDecoration(color: FC.surface, borderRadius: BorderRadius.circular(12), border: Border.all(color: FC.line)),
        child: LayoutBuilder(builder: (context, cons) {
          final price = AnimatedSwitcher(
            duration: const Duration(milliseconds: 350),
            child: FcText('${ugx(livePrices.price(s.id, f))}/L', key: ValueKey(livePrices.price(s.id, f)), kind: Tx.subtitle, color: FC.gold, maxLines: 1),
          );
          final change = FcText(_pill(s.id, f), kind: Tx.caption, color: FC.muted, maxLines: 1);
          final copy = Column(crossAxisAlignment: CrossAxisAlignment.start, children: [FcText(name, kind: Tx.subtitle), FcText(sub, kind: Tx.caption, color: FC.muted)]);
          // Phones put the price under the product name so long prices and
          // enlarged system text never push past the card edge.
          if (cons.maxWidth < 320) {
            return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              Row(children: [
                IconBox(IconName.fuel),
                const SizedBox(width: 12),
                Expanded(child: copy),
              ]),
              const SizedBox(height: 10),
              Wrap(spacing: 10, runSpacing: 4, crossAxisAlignment: WrapCrossAlignment.center, children: [price, change]),
            ]);
          }
          return Row(children: [
            IconBox(IconName.fuel),
            const SizedBox(width: 12),
            Expanded(child: copy),
            const SizedBox(width: 8),
            Column(crossAxisAlignment: CrossAxisAlignment.end, children: [price, change]),
          ]);
        }),
      );

  String _ago(DateTime t) {
    final d = DateTime.now().difference(t);
    if (d.inSeconds < 45) return 'just now';
    if (d.inMinutes < 60) return '${d.inMinutes}m ago';
    return '${d.inHours}h ago';
  }

  Widget _activity(LiveStation s) {
    final ev = livePrices.events.where((e) => e.stationId == s.id).take(5).toList();
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      const SectionHeading('Price activity', caption: 'How recent orders moved the price'),
      if (ev.isEmpty)
        FcText('No orders yet. Prices are at the station’s pump price.', kind: Tx.caption, color: FC.muted)
      else
        for (final e in ev)
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Row(children: [
              Icon(e.pct > 0 ? Icons.arrow_upward : Icons.remove, size: 14, color: FC.gold),
              const SizedBox(width: 8),
              Expanded(
                child: FcText(
                  '${e.fuel == FuelType.petrol ? 'Petrol' : 'Diesel'} · ${e.attempt ? 'order started' : '${e.litres.round()} L ordered'}',
                  kind: Tx.caption,
                  color: FC.muted,
                ),
              ),
              FcText('${e.pct >= 0 ? '+' : '−'}${e.pct.abs().toStringAsFixed(2)}% · ${_ago(e.at)}', kind: Tx.caption),
            ]),
          ),
    ]);
  }

  @override
  Widget build(BuildContext context) => AnimatedBuilder(animation: livePrices, builder: (_, __) => _page(context));

  Widget _page(BuildContext context) {
    final s = livePrices.selected;
    final wide = isWide(context);
    final coverH = math.max(360.0, vh(context) * (wide ? .58 : .47));
    final pad = cl(context, 18, 5, 50);
    final tpad = cl(context, 20, 6, 70);

    // "Best price nearby" goes to whichever station has the lower petrol price right now.
    final cheapest = stationNetwork.all.reduce((a, b) => livePrices.price(a.id, FuelType.petrol) <= livePrices.price(b.id, FuelType.petrol) ? a : b);

    final cover = SizedBox(
      height: coverH,
      child: Stack(fit: StackFit.expand, children: [
        Image.asset('assets/images/station-hero.png', fit: BoxFit.cover),
        const DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter, colors: [Color(0x40000000), Color(0x00000000), Colors.black], stops: [0, .3, 1]),
          ),
        ),
        Positioned(
          top: topInset(context) + 18,
          left: pad,
          right: math.max(pad, kRightInset),
          child: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
            FcButton.icon(IconName.arrow, key: const ValueKey('page-back'), onTap: () => app.backOr(Screen.home)),
            Tap(
              onTap: () {
                setState(() => app.stationSaved = !app.stationSaved);
                toast(context, app.stationSaved ? 'Station saved to your favourites.' : 'Removed from favourites.');
              },
              child: Container(
                width: 42,
                height: 42,
                decoration: BoxDecoration(color: const Color(0xC20C0E11), borderRadius: BorderRadius.circular(12), border: Border.all(color: al(Colors.white, .12))),
                child: Center(child: Ic(IconName.star, size: 18, color: app.stationSaved ? FC.gold : FC.ink, filled: app.stationSaved)),
              ),
            ),
          ]),
        ),
        Positioned(
          left: tpad,
          right: tpad,
          bottom: 26,
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              StationLogo(s, size: 54),
              const SizedBox(width: 12),
              const VerifiedPill('Verified partner', check: true, iconSize: 14),
            ]),
            const SizedBox(height: 10),
            FcText(s.brand.toUpperCase(), kind: Tx.label, color: FC.gold),
            const SizedBox(height: 8),
            FcText(s.name, kind: Tx.display),
            const SizedBox(height: 8),
            FcText(s.address, kind: Tx.caption, color: FC.muted),
          ]),
        ),
      ]),
    );

    return AppPage(
      body: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        cover,
        Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 850),
            child: Padding(
              padding: EdgeInsets.fromLTRB(tpad, 8, tpad, 44 + bottomInset(context)),
              child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                Container(
                  padding: const EdgeInsets.fromLTRB(0, 18, 0, 24),
                  decoration: BoxDecoration(border: Border(bottom: BorderSide(color: FC.line))),
                  child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    _stat(IconName.star, '${s.rating}', '${s.reviews} reviews'),
                    _stat(IconName.location, '${s.km} km', 'Distance'),
                    _stat(IconName.clock, '${s.etaMin}–${s.etaMax}', 'Minutes', last: true),
                  ]),
                ),
                SectionHeading('Live prices', trailing: cheapest.id == s.id ? const VerifiedPill('Best price nearby') : const LivePill('Live')),
                _product(s, 'Premium Petrol', '95 octane · cleaner performance', FuelType.petrol),
                const SizedBox(height: 10),
                _product(s, 'Ultra Diesel', 'High efficiency · low sulphur', FuelType.diesel),
                const SizedBox(height: 22),
                _activity(s),
                const SizedBox(height: 22),
                FcButton('Choose fuel', trailingIcon: IconName.arrow, onTap: () {
                  livePrices.recordAttempt(s.id, FuelType.petrol);
                  livePrices.recordAttempt(s.id, FuelType.diesel);
                  widget.go(Screen.fuel);
                }),
              ]),
            ),
          ),
        ),
      ]),
    );
  }
}

// ===========================================================================
// Live fuel prices (Stabex + Shell)
// ===========================================================================
enum FuelType { petrol, diesel }

/// Static info for the stations we currently serve. Add new stations here as you grow.
class LiveStation {
  final String id, name, brand, address, logoAsset;
  final double km, rating;
  final int reviews, etaMin, etaMax;
  final Map<FuelType, int> basePrice; // UGX per litre
  final double lat, lng; // forecourt coordinates, used by the live map
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
    required this.lat,
    required this.lng,
  });

  LatLng get point => LatLng(lat, lng);
}

const kLiveStations = <LiveStation>[
  LiveStation(
    id: 'stabex',
    name: 'Stabex Kira Road',
    brand: 'Stabex',
    address: 'Kira Road, Kampala · Open 24 hours',
    logoAsset: 'assets/images/stabex.png',
    km: 1.8,
    rating: 4.9,
    reviews: 320,
    etaMin: 18,
    etaMax: 24,
    basePrice: {FuelType.petrol: 6850, FuelType.diesel: 7150}, // Stabex Kampala, Nov 2026 estimate
    lat: 0.3392,
    lng: 32.5931,
  ),
  LiveStation(
    id: 'shell',
    name: 'Shell Jinja Road',
    brand: 'Shell',
    address: 'Jinja Road, Kampala · Open 24 hours',
    logoAsset: 'assets/images/shell_logo.png',
    km: 2.4,
    rating: 4.8,
    reviews: 275,
    etaMin: 20,
    etaMax: 27,
    basePrice: {FuelType.petrol: 6950, FuelType.diesel: 7290}, // Shell Kampala, Nov 2026 estimate
    lat: 0.3316,
    lng: 32.6104,
  ),
];

/// The live station network. Seeded with [kLiveStations] and extended by the
/// "Add a station" flow on the home screen, so a new forecourt shows up on the
/// home list, the map and the price board without restarting the app.
class StationNetwork extends ChangeNotifier {
  final List<LiveStation> _all = List.of(kLiveStations);

  List<LiveStation> get all => List.unmodifiable(_all);

  void add(LiveStation s) {
    _all.add(s);
    notifyListeners();
  }

  LiveStation byId(String id) => _all.firstWhere((s) => s.id == id);
}

final stationNetwork = StationNetwork();

/// One line in the price activity feed.
class PriceEvent {
  final String stationId;
  final FuelType fuel;
  final double litres;
  final double pct; // price change caused by this event
  final bool attempt; // true = someone opened ordering, false = order placed
  final DateTime at;
  PriceEvent(this.stationId, this.fuel, this.litres, this.pct, this.attempt) : at = DateTime.now();
}

/// Live prices. Demand pressure (litres) pushes a station's price UP as people
/// order or start to order; pressure decays every 20 s so the price drifts DOWN
/// again. Percentages are always measured against the station's base price.
///
/// Base prices are the pump prices in [kLiveStations]. Keep them in sync with
/// what your stations really charge (ideally pushed from your backend through
/// [setBase]). Orders only move the price on this device until you wire the
/// backend; see [applyRemote].
class LivePrices extends ChangeNotifier {
  LivePrices() {
    _timer = Timer.periodic(const Duration(seconds: 20), (_) => _decay());
  }

  static const _pctPer100L = 0.15; // % price rise per 100 litres ordered
  static const _maxPremiumPct = 3.0; // price never rises more than 3% above base
  static const _attemptLitres = 10.0; // pressure from someone just opening an order

  final Map<String, Map<FuelType, double>> _demand = {};
  final Map<String, Map<FuelType, int>> _remote = {};
  final Map<String, Map<FuelType, int>> _baseOverride = {};
  final Map<String, Map<FuelType, int>> _lastMove = {};
  final Map<String, Map<FuelType, double>> _lastMovePct = {};
  final List<PriceEvent> events = [];
  Timer? _timer;

  String selectedId = kLiveStations.first.id;

  LiveStation byId(String id) => stationNetwork.byId(id);
  LiveStation get selected => byId(selectedId);

  int base(String id, FuelType f) => _baseOverride[id]?[f] ?? byId(id).basePrice[f]!;

  /// Update a station's real pump price (e.g. from your backend / admin panel).
  void setBase(String id, FuelType f, int ugx) {
    _baseOverride.putIfAbsent(id, () => {})[f] = ugx;
    notifyListeners();
  }

  double _premiumPct(String id, FuelType f) {
    final d = _demand[id]?[f] ?? 0;
    return (d / 100 * _pctPer100L).clamp(0.0, _maxPremiumPct);
  }

  int price(String id, FuelType f) {
    final r = _remote[id]?[f];
    if (r != null) return r;
    return (base(id, f) * (1 + _premiumPct(id, f) / 100)).round();
  }

  /// % difference vs. the station's base price.
  double changePct(String id, FuelType f) => (price(id, f) - base(id, f)) / base(id, f) * 100;

  int lastMove(String id, FuelType f) => _lastMove[id]?[f] ?? 0;
  double lastMovePct(String id, FuelType f) => _lastMovePct[id]?[f] ?? 0;

  double get petrolAverage => stationNetwork.all.map((s) => price(s.id, FuelType.petrol)).reduce((a, b) => a + b) / stationNetwork.all.length;

  void _bump(String id, FuelType f, double litres, bool attempt) {
    final before = price(id, f);
    final m = _demand.putIfAbsent(id, () => {});
    m[f] = (m[f] ?? 0) + litres;
    final after = price(id, f);
    final pct = (after - before) / before * 100;
    _lastMove.putIfAbsent(id, () => {})[f] = after - before;
    _lastMovePct.putIfAbsent(id, () => {})[f] = pct;
    events.insert(0, PriceEvent(id, f, litres, pct, attempt));
    if (events.length > 40) events.removeLast();
    notifyListeners();
  }

  /// Call when an order is confirmed.
  void recordOrder(String stationId, FuelType fuel, double litres) => _bump(stationId, fuel, litres, false);

  /// Call when someone starts ordering (opens fuel selection). Small bump.
  void recordAttempt(String stationId, FuelType fuel) => _bump(stationId, fuel, _attemptLitres, true);

  /// Hook for server-pushed prices.
  void applyRemote(String stationId, FuelType fuel, int ugx) {
    final before = price(stationId, fuel);
    _remote.putIfAbsent(stationId, () => {})[fuel] = ugx;
    _lastMove.putIfAbsent(stationId, () => {})[fuel] = ugx - before;
    _lastMovePct.putIfAbsent(stationId, () => {})[fuel] = (ugx - before) / before * 100;
    notifyListeners();
  }

  void _decay() {
    var changed = false;
    for (final sid in _demand.keys) {
      final e = _demand[sid]!;
      for (final f in e.keys.toList()) {
        if (e[f]! > 1) {
          final before = price(sid, f);
          e[f] = e[f]! * 0.92;
          final after = price(sid, f);
          if (after != before) {
            _lastMove.putIfAbsent(sid, () => {})[f] = after - before;
            _lastMovePct.putIfAbsent(sid, () => {})[f] = (after - before) / before * 100;
          }
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

// ---------------------------------------------------------------------------
// Add a station (home CTA). Saves to [stationNetwork] on this device — swap
// [_AddStationFormState._save] for `POST /stations` once the backend exists.
// ---------------------------------------------------------------------------
Future<bool?> showAddStationSheet(BuildContext context) =>
    showFcSheet<bool>(context, title: 'Add a station', builder: (ctx) => const _AddStationForm());

class _AddStationForm extends StatefulWidget {
  const _AddStationForm();
  @override
  State<_AddStationForm> createState() => _AddStationFormState();
}

class _AddStationFormState extends State<_AddStationForm> {
  static const _brands = ['Stabex', 'Shell', 'TotalEnergies', 'Other'];
  final _name = TextEditingController();
  final _address = TextEditingController();
  final _petrol = TextEditingController();
  final _diesel = TextEditingController();
  String _brand = 'Stabex';
  String? _nameErr, _addressErr, _petrolErr, _dieselErr;

  /// Brand logos we already ship. Unknown brands fall back to their initial.
  String get _logoAsset => switch (_brand) {
        'Stabex' => 'assets/images/stabex.png',
        'Shell' => 'assets/images/shell_logo.png',
        _ => '',
      };

  @override
  void dispose() {
    _name.dispose();
    _address.dispose();
    _petrol.dispose();
    _diesel.dispose();
    super.dispose();
  }

  void _save() {
    final name = _name.text.trim();
    final address = _address.text.trim();
    final petrol = int.tryParse(_petrol.text.trim());
    final diesel = int.tryParse(_diesel.text.trim());
    setState(() {
      _nameErr = name.length < 3 ? 'Enter the station name' : null;
      _addressErr = address.length < 3 ? 'Enter the street or area' : null;
      _petrolErr = (petrol == null || petrol < 1000) ? 'Enter a price' : null;
      _dieselErr = (diesel == null || diesel < 1000) ? 'Enter a price' : null;
    });
    if (_nameErr != null || _addressErr != null || _petrolErr != null || _dieselErr != null) return;
    final rnd = math.Random();
    final etaMin = 20 + rnd.nextInt(5);
    stationNetwork.add(LiveStation(
      id: '${_brand.toLowerCase()}-${DateTime.now().millisecondsSinceEpoch}',
      name: name,
      brand: _brand,
      address: address,
      logoAsset: _logoAsset,
      // Rough placeholders until the forecourt is geocoded.
      km: 2.5 + rnd.nextInt(7),
      rating: 5,
      reviews: 0,
      etaMin: etaMin,
      etaMax: etaMin + 6 + rnd.nextInt(4),
      basePrice: {FuelType.petrol: petrol!, FuelType.diesel: diesel!},
      lat: 0.335 + (rnd.nextDouble() - .5) * .05,
      lng: 32.60 + (rnd.nextDouble() - .5) * .05,
    ));
    Navigator.of(context).pop(true);
  }

  @override
  Widget build(BuildContext context) => Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        FcText('BRAND', kind: Tx.label, color: FC.gold),
        const SizedBox(height: 10),
        Wrap(spacing: 8, runSpacing: 8, children: [
          for (final b in _brands)
            Tap(
              onTap: () => setState(() => _brand = b),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 8),
                decoration: BoxDecoration(
                  color: _brand == b ? al(FC.gold, .1) : FC.surface2,
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: _brand == b ? FC.gold : FC.line),
                ),
                child: Text(b, style: fs(10.88, color: _brand == b ? FC.gold : FC.muted)),
              ),
            ),
        ]),
        const SizedBox(height: 16),
        FcField(label: 'Station name', hint: 'e.g. Shell Ntinda', icon: IconName.fuel, controller: _name, error: _nameErr, action: TextInputAction.next),
        const SizedBox(height: 14),
        FcField(label: 'Address', hint: 'Street or area, city', icon: IconName.location, controller: _address, error: _addressErr, action: TextInputAction.next),
        const SizedBox(height: 14),
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Expanded(
            child: FcField(
              label: 'Petrol (UGX/L)',
              hint: '6850',
              icon: IconName.drop,
              controller: _petrol,
              keyboard: TextInputType.number,
              formatters: [FilteringTextInputFormatter.digitsOnly, LengthLimitingTextInputFormatter(6)],
              error: _petrolErr,
              action: TextInputAction.next,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: FcField(
              label: 'Diesel (UGX/L)',
              hint: '7150',
              icon: IconName.drop,
              controller: _diesel,
              keyboard: TextInputType.number,
              formatters: [FilteringTextInputFormatter.digitsOnly, LengthLimitingTextInputFormatter(6)],
              error: _dieselErr,
              action: TextInputAction.done,
              onSubmitted: (_) => _save(),
            ),
          ),
        ]),
        const SizedBox(height: 8),
        FcText('New stations are saved on this device until the backend is connected.', kind: Tx.caption, color: FC.muted),
        const SizedBox(height: 16),
        FcButton('Add station', icon: IconName.plus, onTap: _save),
      ]);
}

String ugx(num v) {
  final s = v.round().toString();
  final b = StringBuffer();
  for (var i = 0; i < s.length; i++) {
    if (i > 0 && (s.length - i) % 3 == 0) b.write(',');
    b.write(s[i]);
  }
  return 'UGX $b';
}