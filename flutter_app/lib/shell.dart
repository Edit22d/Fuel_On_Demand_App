import 'package:flutter/material.dart';
import 'core/core.dart';
import 'screens/account_screens.dart';
import 'screens/auth_screens.dart';
import 'screens/browse_screens.dart';
import 'screens/extra_customer_screens.dart';
import 'screens/missing_screens.dart';
import 'screens/order_screens.dart';
import 'screens/rider_screens.dart';

/// Hosts the active screen and animates swaps between them.
///
/// Navigation is still driven by [AppState.go]/[AppState.back] so the hardware
/// back button and deep links behave like a real router.
class Shell extends StatelessWidget {
  const Shell({super.key});

  Widget _screen(Screen s) {
    final go = app.go;
    switch (s) {
      case Screen.splash:
        return SplashScreen(go: go);
      case Screen.onboarding:
        return OnboardingScreen(go: go);
      case Screen.login:
        return LoginScreen(go: go);
      case Screen.signup:
        return SignupScreen(go: go);
      case Screen.forgot:
        return ForgotScreen(go: go);
      case Screen.otp:
        return OtpScreen(go: go);
      case Screen.newPassword:
        return NewPasswordScreen(go: go);
      case Screen.locationAccess:
        return LocationAccessScreen(go: go);
      case Screen.home:
        return HomeScreen(go: go);
      case Screen.partners:
        return PartnersScreen(go: go);
      case Screen.station:
        return StationScreen(go: go);
      case Screen.fuel:
        return FuelScreen(go: go);
      case Screen.vehicle:
        return VehicleScreen(go: go);
      case Screen.checkout:
        return CheckoutScreen(go: go);
      case Screen.payment:
        return PaymentScreen(go: go);
      case Screen.tracking:
        return TrackingScreen(go: go);
      case Screen.success:
        return SuccessScreen(go: go);
      case Screen.orders:
        return OrdersScreen(go: go);
      case Screen.orderDetail:
        return OrderDetailScreen(go: go);
      case Screen.wallet:
        return WalletScreen(go: go);
      case Screen.rewards:
        return RewardsScreen(go: go);
      case Screen.notifications:
        return NotificationsScreen(go: go);
      case Screen.profile:
        return ProfileScreen(go: go);
      case Screen.addresses:
        return AddressesScreen(go: go);
      case Screen.vehicles:
        return VehiclesScreen(go: go);
      case Screen.support:
        return SupportScreen(go: go);
      case Screen.safety:
        return SafetyScreen(go: go);
      case Screen.orderConfirmation:
        return OrderConfirmationScreen(go: go);
      case Screen.cancelOrder:
        return CancelOrderScreen(go: go);
      case Screen.editProfile:
        return EditProfileScreen(go: go);
      case Screen.appSettings:
        return AppSettingsScreen(go: go);
      case Screen.riderRegistration:
        return RiderRegistrationScreen(go: go);
      case Screen.riderLogin:
        return RiderLoginScreen(go: go);
      case Screen.riderDashboard:
        return RiderDashboardScreen(go: go);
      case Screen.riderDeliveries:
        return RiderDeliveriesScreen(go: go);
      case Screen.riderRequest:
        return RiderRequestScreen(go: go);
      case Screen.riderDecision:
        return RiderDecisionScreen(go: go);
      case Screen.riderNavigation:
        return RiderNavigationScreen(go: go);
      case Screen.riderPickup:
        return RiderPickupScreen(go: go);
      case Screen.riderDelivery:
        return RiderDeliveryScreen(go: go);
      case Screen.riderEarnings:
        return RiderEarningsScreen(go: go);
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: app,
      builder: (context, _) => PopScope(
        canPop: !app.canGoBack,
        onPopInvokedWithResult: (didPop, result) {
          if (!didPop) app.back();
        },
        child: Scaffold(
          backgroundColor: FC.black,
          body: AnimatedSwitcher(
            duration: Motion.page,
            reverseDuration: const Duration(milliseconds: 200),
            switchInCurve: Motion.soft,
            switchOutCurve: Curves.easeOut,
            transitionBuilder: (child, animation) => PageSwap(animation: animation, child: child),
            layoutBuilder: (current, previous) => Stack(
              fit: StackFit.expand,
              children: [
                for (final p in previous) Positioned.fill(child: IgnorePointer(child: p)),
                if (current != null) Positioned.fill(child: current),
              ],
            ),
            child: KeyedSubtree(key: ValueKey(app.current), child: _screen(app.current)),
          ),
        ),
      ),
    );
  }
}