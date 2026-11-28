import 'dart:async';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';

import 'icons.dart';
import 'map_style.dart';
import 'motion.dart';
import 'theme.dart';

/// A rounded, themed map surface.
///
/// Uses the Google Maps SDK on Android/iOS (and on web when an API key is
/// supplied) and falls back to a hand-painted dark preview on every other
/// platform, so the app never shows a broken map or a red error box.
class LiveMap extends StatefulWidget {
  final LatLng? center;
  final LatLng? driver;
  final LatLng? pickup;
  final LatLng? destination;
  final List<LatLng> route;
  final double? height;
  final double radius;
  final bool follow;
  final bool myLocation;
  final bool interactive;
  final bool showRecenter;
  final bool showRoute;
  final EdgeInsets padding;
  final ValueChanged<LatLng>? onTap;
  final Widget? overlay;
  final Widget? footer;
  final bool previewLabel;

  const LiveMap({
    super.key,
    this.center,
    this.driver,
    this.pickup,
    this.destination,
    this.route = const [],
    this.height,
    this.radius = 20,
    this.follow = true,
    this.myLocation = false,
    this.interactive = true,
    this.showRecenter = true,
    this.showRoute = true,
    this.padding = const EdgeInsets.only(bottom: 110),
    this.onTap,
    this.overlay,
    this.footer,
    this.previewLabel = true,
  });

  @override
  State<LiveMap> createState() => _LiveMapState();
}

class _LiveMapState extends State<LiveMap> {
  GoogleMapController? _map;
  BitmapDescriptor? _driverPin, _pickupPin, _destPin;

  @override
  void initState() {
    super.initState();
    _loadPins();
  }

  Future<void> _loadPins() async {
    if (!MapConfig.enabled) return;
    final dark = FC.dark;
    final pins = await Future.wait([
      _circlePin(Icons.local_shipping_rounded, FC.gold, const Color(0xFF111111), 'd$dark'),
      _circlePin(Icons.local_gas_station_rounded, FC.surface2, FC.gold, 'p$dark'),
      _circlePin(Icons.location_on_rounded, FC.gold, const Color(0xFF111111), 't$dark'),
    ]);
    if (!mounted) return;
    setState(() {
      _driverPin = pins[0];
      _pickupPin = pins[1];
      _destPin = pins[2];
    });
  }

  static final Map<String, BitmapDescriptor> _pinCache = {};

  Future<BitmapDescriptor> _circlePin(IconData icon, Color bg, Color fg, String cacheKey) async {
    final cached = _pinCache[cacheKey];
    if (cached != null) return cached;
    const size = 112.0;
    final recorder = ui.PictureRecorder();
    final canvas = Canvas(recorder);
    const c = Offset(size / 2, size / 2);
    canvas.drawCircle(c, size * .46, Paint()..color = bg.withValues(alpha: .18));
    canvas.drawCircle(c, size * .33, Paint()..color = bg);
    canvas.drawCircle(
      c,
      size * .33,
      Paint()
        ..color = fg.withValues(alpha: .35)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 3,
    );
    final tp = TextPainter(
      textDirection: TextDirection.ltr,
      text: TextSpan(
        text: String.fromCharCode(icon.codePoint),
        style: TextStyle(
          fontSize: size * .34,
          fontFamily: icon.fontFamily,
          package: icon.fontPackage,
          color: fg,
          height: 1,
        ),
      ),
    )..layout();
    tp.paint(canvas, c - Offset(tp.width / 2, tp.height / 2));
    final image = await recorder.endRecording().toImage(size.toInt(), size.toInt());
    final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
    image.dispose();
    final pin = BitmapDescriptor.bytes(bytes!.buffer.asUint8List());
    _pinCache[cacheKey] = pin;
    return pin;
  }

  List<LatLng> get _allPoints => [
        if (widget.pickup != null) widget.pickup!,
        if (widget.destination != null) widget.destination!,
        if (widget.driver != null) widget.driver!,
        ...widget.route,
      ];

  LatLng get _initialTarget =>
      widget.driver ?? widget.destination ?? widget.pickup ?? widget.center ?? MapConfig.kampala;

  @override
  void didUpdateWidget(covariant LiveMap old) {
    super.didUpdateWidget(old);
    final d = widget.driver;
    if (d == null || !widget.follow || _map == null) return;
    if (old.driver == d) return;
    _map!.animateCamera(CameraUpdate.newLatLng(d));
  }

  Future<void> _onCreated(GoogleMapController c) async {
    _map = c;
    await Future<void>.delayed(const Duration(milliseconds: 320));
    if (!mounted) return;
    await _frame(animate: false);
  }

  Future<void> _frame({bool animate = true}) async {
    final map = _map;
    if (map == null) return;
    final pts = _allPoints;
    if (pts.isEmpty) {
      final update = CameraUpdate.newLatLngZoom(_initialTarget, 14.6);
      animate ? map.animateCamera(update) : map.moveCamera(update);
      return;
    }
    if (pts.length == 1) {
      final update = CameraUpdate.newLatLngZoom(pts.first, 15.4);
      animate ? map.animateCamera(update) : map.moveCamera(update);
      return;
    }
    var south = pts.first.latitude, north = pts.first.latitude;
    var west = pts.first.longitude, east = pts.first.longitude;
    for (final p in pts) {
      south = math.min(south, p.latitude);
      north = math.max(north, p.latitude);
      west = math.min(west, p.longitude);
      east = math.max(east, p.longitude);
    }
    final bounds = LatLngBounds(
      southwest: LatLng(south, west),
      northeast: LatLng(north, east),
    );
    final update = CameraUpdate.newLatLngBounds(bounds, 58);
    animate ? map.animateCamera(update) : map.moveCamera(update);
  }

  Future<void> _recenter() async {
    if (widget.driver != null) {
      final map = _map;
      if (map == null) return;
      await map.animateCamera(CameraUpdate.newLatLngZoom(widget.driver!, 15.8));
      return;
    }
    await _frame();
  }

  Set<Marker> _markers() {
    final out = <Marker>{};
    if (widget.pickup != null) {
      out.add(Marker(
        markerId: const MarkerId('pickup'),
        position: widget.pickup!,
        icon: _pickupPin ?? BitmapDescriptor.defaultMarkerWithHue(BitmapDescriptor.hueOrange),
        anchor: const Offset(.5, .5),
        infoWindow: const InfoWindow(title: 'Pickup station'),
      ));
    }
    if (widget.destination != null) {
      out.add(Marker(
        markerId: const MarkerId('destination'),
        position: widget.destination!,
        icon: _destPin ?? BitmapDescriptor.defaultMarkerWithHue(BitmapDescriptor.hueYellow),
        anchor: const Offset(.5, .5),
        infoWindow: const InfoWindow(title: 'Delivery location'),
      ));
    }
    if (widget.driver != null) {
      out.add(Marker(
        markerId: const MarkerId('driver'),
        position: widget.driver!,
        icon: _driverPin ?? BitmapDescriptor.defaultMarkerWithHue(BitmapDescriptor.hueYellow),
        anchor: const Offset(.5, .5),
        flat: true,
      ));
    }
    return out;
  }

  Set<Polyline> _polylines() {
    if (!widget.showRoute) return const {};
    final pts = widget.route.isNotEmpty
        ? widget.route
        : [
            if (widget.pickup != null) widget.pickup!,
            if (widget.destination != null) widget.destination!,
          ];
    if (pts.length < 2) return const {};
    return {
      Polyline(
        polylineId: const PolylineId('route'),
        points: pts,
        width: 9,
        color: FC.gold.withValues(alpha: .16),
        jointType: JointType.round,
      ),
      Polyline(
        polylineId: const PolylineId('route-core'),
        points: pts,
        width: 4,
        color: FC.gold,
        jointType: JointType.round,
        patterns: [PatternItem.dash(14), PatternItem.gap(10)],
      ),
    };
  }

  Set<Circle> _circles() {
    final out = <Circle>{};
    if (widget.driver != null) {
      out.add(Circle(
        circleId: const CircleId('driver-glow'),
        center: widget.driver!,
        radius: 55,
        fillColor: FC.gold.withValues(alpha: .10),
        strokeColor: FC.gold.withValues(alpha: .30),
        strokeWidth: 1,
      ));
    }
    if (widget.destination != null) {
      out.add(Circle(
        circleId: const CircleId('dest-glow'),
        center: widget.destination!,
        radius: 40,
        fillColor: FC.ink.withValues(alpha: .05),
        strokeColor: FC.ink.withValues(alpha: .18),
        strokeWidth: 1,
      ));
    }
    return out;
  }

  @override
  Widget build(BuildContext context) {
    final content = MapConfig.enabled ? _google(context) : _preview(context);
    return SizedBox(
      height: widget.height,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(widget.radius),
        child: Stack(fit: StackFit.expand, children: [
          content,
          if (widget.overlay != null) widget.overlay!,
          if (widget.showRecenter && MapConfig.enabled)
            Positioned(
              right: 12,
              bottom: widget.footer != null ? 132 : 92,
              child: _MapButton(icon: Icons.my_location_rounded, onTap: _recenter, label: 'Recenter map'),
            ),
          if (widget.footer != null)
            Positioned(left: 10, right: 10, bottom: 10, child: widget.footer!),
        ]),
      ),
    );
  }

  Widget _google(BuildContext context) => GoogleMap(
        initialCameraPosition: CameraPosition(target: _initialTarget, zoom: 14.6),
        onMapCreated: _onCreated,
        style: MapConfig.darkStyle,
        markers: _markers(),
        polylines: _polylines(),
        circles: _circles(),
        myLocationEnabled: widget.myLocation,
        myLocationButtonEnabled: false,
        compassEnabled: false,
        mapToolbarEnabled: false,
        zoomControlsEnabled: false,
        rotateGesturesEnabled: false,
        tiltGesturesEnabled: false,
        scrollGesturesEnabled: widget.interactive,
        zoomGesturesEnabled: widget.interactive,
        padding: widget.padding,
        onTap: widget.onTap,
      );

  Widget _preview(BuildContext context) => Stack(fit: StackFit.expand, children: [
        _PreviewSurface(
          driver: widget.driver,
          pickup: widget.pickup,
          destination: widget.destination,
          route: widget.route,
        ),
        if (widget.previewLabel)
          Positioned(
            left: 12,
            top: 12,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
              decoration: BoxDecoration(
                color: al(FC.black, .66),
                borderRadius: BorderRadius.circular(20),
                border: Border.all(color: al(FC.overlay, .10)),
              ),
              child: Row(mainAxisSize: MainAxisSize.min, children: [
                PulseDot(color: FC.gold, size: 4),
                const SizedBox(width: 3),
                Text('MAP PREVIEW', style: fs(8.2, color: FC.gold, w: FontWeight.w800, ls: .8, h: 1.3)),
              ]),
            ),
          ),
      ]);
}

class _MapButton extends StatelessWidget {
  final IconData icon;
  final VoidCallback onTap;
  final String label;
  const _MapButton({required this.icon, required this.onTap, required this.label});

  @override
  Widget build(BuildContext context) => Semantics(
        button: true,
        label: label,
        child: Pressable(
          onTap: onTap,
          scale: .92,
          child: Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: al(FC.surface, .92),
              border: Border.all(color: FC.line),
              boxShadow: [BoxShadow(color: al(Colors.black, .35), blurRadius: 18, offset: const Offset(0, 6))],
            ),
            child: Icon(icon, size: 18, color: FC.gold),
          ),
        ),
      );
}

// ---------------------------------------------------------------------------
// Hand-painted preview map (no API key / unsupported platform)
// ---------------------------------------------------------------------------
class _PreviewSurface extends StatelessWidget {
  final LatLng? driver;
  final LatLng? pickup;
  final LatLng? destination;
  final List<LatLng> route;

  const _PreviewSurface({this.driver, this.pickup, this.destination, this.route = const []});

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(builder: (context, cons) {
      final pts = [
        if (pickup != null) pickup!,
        if (destination != null) destination!,
        ...route,
        if (driver != null) driver!,
      ];
      final project = _Projector(pts, Size(cons.maxWidth, cons.maxHeight));
      return Stack(fit: StackFit.expand, children: [
        CustomPaint(painter: _PreviewPainter(
          points: [for (final p in route) project(p)],
          pickup: pickup == null ? null : project(pickup!),
          destination: destination == null ? null : project(destination!),
        )),
        if (pickup != null)
          Positioned(
            left: project(pickup!).dx - 15,
            top: project(pickup!).dy - 15,
            child: _dot(FC.surface2, FC.gold, IconName.fuel),
          ),
        if (destination != null)
          Positioned(
            left: project(destination!).dx - 15,
            top: project(destination!).dy - 15,
            child: _dot(FC.gold, const Color(0xFF111111), IconName.location),
          ),
        if (driver != null) _DriverDot(position: project(driver!)),
      ]);
    });
  }

  Widget _dot(Color bg, Color fg, IconName icon) => Container(
        width: 30,
        height: 30,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: bg,
          border: Border.all(color: al(FC.overlay, .18)),
          boxShadow: [BoxShadow(color: al(Colors.black, .45), blurRadius: 12, offset: const Offset(0, 4))],
        ),
        child: Center(child: Ic(icon, size: 14, color: fg)),
      );
}

/// Animates the driver marker between two coordinates so movement looks live.
class _DriverDot extends StatefulWidget {
  final Offset position;
  const _DriverDot({required this.position});

  @override
  State<_DriverDot> createState() => _DriverDotState();
}

class _DriverDotState extends State<_DriverDot> with SingleTickerProviderStateMixin {
  late final AnimationController _c =
      AnimationController(vsync: this, duration: const Duration(milliseconds: 900), value: 1);
  late Offset _from = widget.position;
  late Offset _to = widget.position;

  @override
  void didUpdateWidget(covariant _DriverDot old) {
    super.didUpdateWidget(old);
    if (old.position == widget.position) return;
    _from = Offset.lerp(_from, _to, _c.value) ?? _to;
    _to = widget.position;
    _c.forward(from: 0);
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
        animation: _c,
        builder: (context, _) {
          final p = Offset.lerp(_from, _to, Motion.soft.transform(_c.value)) ?? _to;
          return Positioned(
            left: p.dx - 21,
            top: p.dy - 21,
            child: Container(
              width: 42,
              height: 42,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: al(FC.gold, .16),
                boxShadow: [BoxShadow(color: al(FC.gold, .28), blurRadius: 18, spreadRadius: 2)],
              ),
              child: Center(
                child: Container(
                  width: 30,
                  height: 30,
                  decoration: BoxDecoration(shape: BoxShape.circle, color: FC.gold),
                  child: const Center(child: Ic(IconName.truck, size: 15, color: Color(0xFF111111))),
                ),
              ),
            ),
          );
        },
      );
}

/// Maps geo points into the local widget box (equirectangular, good enough for
/// city-scale previews).
class _Projector {
  final double minLat, maxLat, minLng, maxLng;
  final Size size;
  static const _pad = 42.0;

  _Projector(List<LatLng> pts, this.size)
      : minLat = pts.isEmpty ? 0.0 : pts.map((p) => p.latitude).reduce(math.min),
        maxLat = pts.isEmpty ? 1.0 : pts.map((p) => p.latitude).reduce(math.max),
        minLng = pts.isEmpty ? 0.0 : pts.map((p) => p.longitude).reduce(math.min),
        maxLng = pts.isEmpty ? 1.0 : pts.map((p) => p.longitude).reduce(math.max);

  Offset call(LatLng p) {
    final spanLat = (maxLat - minLat).abs() < 1e-6 ? 1e-6 : (maxLat - minLat);
    final spanLng = (maxLng - minLng).abs() < 1e-6 ? 1e-6 : (maxLng - minLng);
    final usableW = math.max(20.0, size.width - _pad * 2);
    final usableH = math.max(20.0, size.height - _pad * 2);
    // Keep the aspect ratio so the street grid never stretches.
    final scale = math.min(usableW / spanLng, usableH / spanLat);
    final x = size.width / 2 + (p.longitude - (minLng + maxLng) / 2) * scale;
    final y = size.height / 2 - (p.latitude - (minLat + maxLat) / 2) * scale;
    return Offset(x, y);
  }
}

class _PreviewPainter extends CustomPainter {
  final List<Offset> points;
  final Offset? pickup;
  final Offset? destination;

  _PreviewPainter({required this.points, this.pickup, this.destination});

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;
    canvas.drawRect(
      rect,
      Paint()
        ..shader = const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF101418), Color(0xFF0A0C0F)],
        ).createShader(rect),
    );

    // Street grid.
    final grid = Paint()
      ..color = al(FC.overlay, .028)
      ..strokeWidth = 1;
    for (double x = 0; x < size.width; x += 34) {
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), grid);
    }
    for (double y = 0; y < size.height; y += 34) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y), grid);
    }

    // Arterial roads.
    final road = Paint()
      ..color = const Color(0xFF1B1F24)
      ..strokeWidth = 16
      ..strokeCap = StrokeCap.round;
    final centre = Paint()
      ..color = al(FC.overlay, .05)
      ..strokeWidth = 1;
    void street(Offset a, Offset b) {
      canvas.drawLine(a, b, road);
      canvas.drawLine(a, b, centre);
    }

    street(Offset(-20, size.height * .78), Offset(size.width + 20, size.height * .30));
    street(Offset(size.width * .12, -20), Offset(size.width * .56, size.height + 20));
    street(Offset(-20, size.height * .22), Offset(size.width + 20, size.height * .46));

    // City blocks.
    final block = Paint()..color = const Color(0xFF14181C);
    final rnd = math.Random(7);
    for (var i = 0; i < 9; i++) {
      final w = 26 + rnd.nextDouble() * 46;
      final h = 22 + rnd.nextDouble() * 40;
      final left = rnd.nextDouble() * (size.width - w);
      final top = rnd.nextDouble() * (size.height - h);
      canvas.drawRRect(
        RRect.fromRectAndRadius(Rect.fromLTWH(left, top, w, h), const Radius.circular(4)),
        block,
      );
    }

    // Route.
    if (points.length >= 2) {
      final path = Path()..moveTo(points.first.dx, points.first.dy);
      for (var i = 1; i < points.length; i++) {
        path.lineTo(points[i].dx, points[i].dy);
      }
      canvas.drawPath(
        path,
        Paint()
          ..color = al(FC.gold, .16)
          ..style = PaintingStyle.stroke
          ..strokeWidth = 14
          ..strokeCap = StrokeCap.round
          ..strokeJoin = StrokeJoin.round,
      );
      canvas.drawPath(
        path,
        Paint()
          ..color = FC.gold
          ..style = PaintingStyle.stroke
          ..strokeWidth = 4
          ..strokeCap = StrokeCap.round
          ..strokeJoin = StrokeJoin.round,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _PreviewPainter old) =>
      old.points != points || old.pickup != pickup || old.destination != destination;
}