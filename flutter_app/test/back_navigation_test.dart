import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:fuelconnect/core/app_state.dart';
import 'package:fuelconnect/core/rider_state.dart';
import 'package:fuelconnect/main.dart';
import 'package:fuelconnect/screens/browse_screens.dart';
import 'package:fuelconnect/services/tracking_service.dart';

/// Navigation guard: every screen that is not an entry point must render a
/// back control (keyed `page-back`) and tapping it must actually leave the
/// screen. This is what keeps users from getting stranded in the order, rider
/// or settings flows after a refactor.
void main() {
  GoogleFonts.config.allowRuntimeFetching = false;

  testWidgets('every screen has a working back control', (tester) async {
    // Phone viewport so the layouts that matter (forms, sheets) are realistic.
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(390, 844);
    await tester.pumpWidget(const FuelOnDemandApp());
    await tester.pump(const Duration(milliseconds: 400));

    // Splash auto-advances, onboarding is the first-run screen and home is the
    // root tab, so none of them has a previous screen to return to.
    const entryPoints = {Screen.splash, Screen.onboarding, Screen.home};

    final back = find.byKey(const ValueKey('page-back'));
    final missing = <String>[];
    final stuck = <String>[];

    for (final screen in Screen.values) {
      if (entryPoints.contains(screen)) continue;

      // Rider screens need a signed-in partner, otherwise the dashboard renders
      // the rider sign-in form instead of its own header.
      rider.signIn();
      app.go(Screen.home, root: true);
      await tester.pump();
      // Let any toast from the previous screen expire: a floating snack bar
      // would sit on top of the next screen's back button.
      await tester.pump(const Duration(seconds: 5));
      app.go(screen);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));

      if (back.evaluate().isEmpty) {
        missing.add(screen.name);
        rider.signOut();
        continue;
      }

      // Long forms put their back action below the fold.
      try {
        await tester.ensureVisible(back.first);
        await tester.pump();
      } catch (_) {
        // Not inside a scrollable — tapping in place is fine.
      }
      await tester.tap(back.first, warnIfMissed: false);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));

      if (app.current == screen) stuck.add(screen.name);
      rider.signOut();
    }

    await tester.pumpWidget(const SizedBox.shrink());
    tester.view.reset();
    tracker.stop();
    livePrices.dispose();

    expect(missing, isEmpty, reason: 'Screens without a back control: ${missing.join(', ')}');
    expect(stuck, isEmpty, reason: 'Back control did not navigate away: ${stuck.join(', ')}');
  });
}
