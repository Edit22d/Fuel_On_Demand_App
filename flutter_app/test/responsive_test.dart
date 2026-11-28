import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:fuelconnect/core/app_state.dart';
import 'package:fuelconnect/core/rider_state.dart';
import 'package:fuelconnect/main.dart';
import 'package:fuelconnect/screens/browse_screens.dart';
import 'package:fuelconnect/services/tracking_service.dart';

/// Layout guard: renders every screen on the device sizes we ship to — small
/// phones, large phones, landscape and tablets — and fails on any overflow or
/// unbounded-constraint error. A second pass repeats the phone sizes with the
/// system font scaled up, which is the most common source of overflows.
void main() {
  GoogleFonts.config.allowRuntimeFetching = false;

  const devices = <String, Size>{
    'small phone 320x568': Size(320, 568),
    'phone 360x640': Size(360, 640),
    'phone 390x844': Size(390, 844),
    'large phone 430x932': Size(430, 932),
    'landscape 812x375': Size(812, 375),
    'tablet 768x1024': Size(768, 1024),
    'desktop 1440x900': Size(1440, 900),
  };

  testWidgets('every screen fits every device size', (tester) async {
    final problems = <String>[];
    var current = 'startup';
    final previousHandler = FlutterError.onError;
    FlutterError.onError = (details) {
      final text = details.toString();
      final where = RegExp(r'[\w_\-/\\]+\.dart:\d+:\d+').firstMatch(text)?.group(0) ?? 'unknown';
      problems.add('$current → ${details.exceptionAsString().split('\n').first}  @  $where');
    };

    Future<void> visitAllScreens(String label) async {
      await tester.pumpWidget(const FuelOnDemandApp());
      await tester.pump(const Duration(milliseconds: 400));
      for (final screen in Screen.values) {
        if (screen == Screen.riderDashboard) {
          // The rider dashboard has a signed-out and a signed-in layout.
          current = '$label · $screen (signed in)';
          rider.signIn();
          app.go(screen, root: true);
          await tester.pump();
          await tester.pump(const Duration(milliseconds: 400));
          rider.signOut();
        }
        current = '$label · $screen';
        app.go(screen, root: true);
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 400));
      }
    }

    for (final device in devices.entries) {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = device.value;
      tester.platformDispatcher.textScaleFactorTestValue = 1;
      await visitAllScreens(device.key);
    }

    // Large system font, which Main clamps to 1.2x.
    for (final device in devices.entries.where((d) => d.value.width <= 430)) {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = device.value;
      tester.platformDispatcher.textScaleFactorTestValue = 1.2;
      await visitAllScreens('${device.key} @1.2x text');
    }

    FlutterError.onError = previousHandler;
    tester.platformDispatcher.clearTextScaleFactorTestValue();
    tester.view.reset();
    await tester.pumpWidget(const SizedBox.shrink());
    tracker.stop();
    livePrices.dispose();

    expect(problems, isEmpty, reason: '\n${problems.join('\n')}\n');
  });
}
