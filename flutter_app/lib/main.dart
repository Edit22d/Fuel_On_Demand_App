import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'core/core.dart';
import 'services/api_client.dart';
import 'services/auth_service.dart';
import 'shell.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
  SystemChrome.setSystemUIOverlayStyle(const SystemUiOverlayStyle(
    statusBarColor: Colors.transparent,
    statusBarIconBrightness: Brightness.light,
    statusBarBrightness: Brightness.dark,
    systemNavigationBarColor: Colors.transparent,
    systemNavigationBarIconBrightness: Brightness.light,
  ));
  await auth.init();
  ApiClient.instance.onUnauthorized = () {
    auth.handleUnauthorized();
    app.go(Screen.login, root: true);
  };
  app.go(auth.isAuthenticated ? Screen.home : Screen.splash, root: true);
  runApp(const FuelOnDemandApp());
}

class FuelOnDemandApp extends StatelessWidget {
  const FuelOnDemandApp({super.key});

  @override
  Widget build(BuildContext context) {
    // Rebuilds the app whenever the theme mode changes.
    return ListenableBuilder(
      listenable: app,
      builder: (context, _) => MaterialApp(
        title: 'FuelOnDemand',
        debugShowCheckedModeBanner: false,
        theme: buildTheme(),
        darkTheme: buildTheme(),
        themeMode: app.themeMode,
        // Keeps layouts intact on devices with very large system font sizes.
        builder: (context, child) {
          final mq = MediaQuery.of(context);
          final icons = app.isDark ? Brightness.light : Brightness.dark;
          return AnnotatedRegion<SystemUiOverlayStyle>(
            value: SystemUiOverlayStyle(
              statusBarColor: Colors.transparent,
              statusBarIconBrightness: icons,
              statusBarBrightness:
                  app.isDark ? Brightness.dark : Brightness.light,
              systemNavigationBarColor: Colors.transparent,
              systemNavigationBarIconBrightness: icons,
            ),
            child: MediaQuery(
              data: mq.copyWith(
                  textScaler: mq.textScaler
                      .clamp(minScaleFactor: 0.9, maxScaleFactor: 1.2)),
              child: child ?? const SizedBox.shrink(),
            ),
          );
        },
        home: const Shell(),
      ),
    );
  }
}
