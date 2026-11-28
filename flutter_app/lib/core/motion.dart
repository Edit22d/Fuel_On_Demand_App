import 'dart:async';
import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'icons.dart';
import 'theme.dart';

// ---------------------------------------------------------------------------
// Motion tokens
// ---------------------------------------------------------------------------
/// One timing system for the whole app, so every screen feels related.
class Motion {
  Motion._();

  static const fast = Duration(milliseconds: 140);
  static const base = Duration(milliseconds: 240);
  static const slow = Duration(milliseconds: 380);
  static const page = Duration(milliseconds: 320);
  static const enter = Duration(milliseconds: 560);
  static const stagger = Duration(milliseconds: 65);

  /// Smooth "UI expo-out" curve used by native delivery apps.
  static const Curve soft = Cubic(.22, 1, .36, 1);
  static const Curve out = Curves.easeOutCubic;
  static const Curve inOut = Curves.easeInOutCubic;
}

/// Light haptic on tap; silently ignored on platforms without a vibrator.
void haptic([HapticFeedbackType type = HapticFeedbackType.light]) {
  switch (type) {
    case HapticFeedbackType.light:
      HapticFeedback.lightImpact();
    case HapticFeedbackType.select:
      HapticFeedback.selectionClick();
    case HapticFeedbackType.heavy:
      HapticFeedback.heavyImpact();
  }
}

enum HapticFeedbackType { light, select, heavy }

// ---------------------------------------------------------------------------
// Pressable — scale + glow feedback wrapper (Cafu-style tactile cards)
// ---------------------------------------------------------------------------
class Pressable extends StatefulWidget {
  final Widget child;
  final VoidCallback? onTap;
  final VoidCallback? onLongPress;
  final double scale;
  final bool glow;
  final BorderRadius? radius;

  const Pressable({
    super.key,
    required this.child,
    this.onTap,
    this.onLongPress,
    this.scale = .975,
    this.glow = false,
    this.radius,
  });

  @override
  State<Pressable> createState() => _PressableState();
}

class _PressableState extends State<Pressable> {
  bool _down = false;

  @override
  Widget build(BuildContext context) {
    final enabled = widget.onTap != null || widget.onLongPress != null;
    return MouseRegion(
      cursor: enabled ? SystemMouseCursors.click : SystemMouseCursors.basic,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTapDown: enabled ? (_) => setState(() => _down = true) : null,
        onTapUp: enabled ? (_) => setState(() => _down = false) : null,
        onTapCancel: enabled ? () => setState(() => _down = false) : null,
        onTap: enabled
            ? () {
                haptic(HapticFeedbackType.light);
                widget.onTap?.call();
              }
            : null,
        onLongPress: widget.onLongPress,
        child: AnimatedScale(
          scale: _down ? widget.scale : 1,
          duration: Motion.fast,
          curve: Motion.out,
          child: AnimatedContainer(
            duration: Motion.fast,
            decoration: BoxDecoration(
              borderRadius: widget.radius,
              boxShadow: widget.glow && _down
                  ? [BoxShadow(color: al(FC.gold, .16), blurRadius: 28, spreadRadius: 2)]
                  : const [],
            ),
            child: widget.child,
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Entrance — staggered fade + rise, plays once when the widget is mounted
// ---------------------------------------------------------------------------
class Entrance extends StatefulWidget {
  final Widget child;
  final int index;
  final double offsetY;
  final Duration duration;
  final Curve curve;

  const Entrance(
    this.child, {
    super.key,
    this.index = 0,
    this.offsetY = 18,
    this.duration = Motion.enter,
    this.curve = Motion.soft,
  });

  @override
  State<Entrance> createState() => _EntranceState();
}

class _EntranceState extends State<Entrance> with SingleTickerProviderStateMixin {
  late final AnimationController _c =
      AnimationController(vsync: this, duration: widget.duration)..value = 0;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    final delay = Motion.stagger * widget.index;
    if (delay == Duration.zero) {
      _c.forward();
    } else {
      _timer = Timer(delay, () {
        if (mounted) _c.forward();
      });
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _c,
      builder: (context, child) {
        final t = widget.curve.transform(_c.value.clamp(0.0, 1.0));
        return Opacity(
          opacity: t,
          child: Transform.translate(offset: Offset(0, (1 - t) * widget.offsetY), child: child),
        );
      },
      child: widget.child,
    );
  }
}

// ---------------------------------------------------------------------------
// CountUp — animated number, keeps money/points feeling live
// ---------------------------------------------------------------------------
class CountUp extends StatelessWidget {
  final num value;
  final TextStyle style;
  final Duration duration;
  final String Function(num)? format;
  final TextAlign? align;

  const CountUp(
    this.value, {
    super.key,
    required this.style,
    this.duration = const Duration(milliseconds: 700),
    this.format,
    this.align,
  });

  @override
  Widget build(BuildContext context) => TweenAnimationBuilder<double>(
        tween: Tween(begin: 0, end: value.toDouble()),
        duration: duration,
        curve: Motion.soft,
        builder: (context, v, _) =>
            Text(format?.call(v) ?? v.round().toString(), style: style, textAlign: align),
      );
}

// ---------------------------------------------------------------------------
// PulseDot — the "live" heartbeat
// ---------------------------------------------------------------------------
class PulseDot extends StatefulWidget {
  final Color color;
  final double size;
  const PulseDot({super.key, required this.color, this.size = 6});

  @override
  State<PulseDot> createState() => _PulseDotState();
}

class _PulseDotState extends State<PulseDot> with SingleTickerProviderStateMixin {
  late final AnimationController _c =
      AnimationController(vsync: this, duration: const Duration(milliseconds: 1600))..repeat();

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: widget.size * 3,
      height: widget.size * 3,
      child: AnimatedBuilder(
        animation: _c,
        builder: (context, _) {
          final t = _c.value;
          return Stack(alignment: Alignment.center, children: [
            Opacity(
              opacity: (1 - t) * .45,
              child: Transform.scale(
                scale: .6 + t * 1.4,
                child: Container(
                  width: widget.size * 2,
                  height: widget.size * 2,
                  decoration: BoxDecoration(shape: BoxShape.circle, color: al(widget.color, .9)),
                ),
              ),
            ),
            Container(
              width: widget.size,
              height: widget.size,
              decoration: BoxDecoration(shape: BoxShape.circle, color: widget.color),
            ),
          ]);
        },
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Shimmer — skeleton placeholders while remote images/data load
// ---------------------------------------------------------------------------
class Shimmer extends StatefulWidget {
  final Widget child;
  final bool active;
  const Shimmer({super.key, required this.child, this.active = true});

  @override
  State<Shimmer> createState() => _ShimmerState();
}

class _ShimmerState extends State<Shimmer> with SingleTickerProviderStateMixin {
  late final AnimationController _c =
      AnimationController(vsync: this, duration: const Duration(milliseconds: 1400))..repeat();

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.active) return widget.child;
    return AnimatedBuilder(
      animation: _c,
      builder: (context, child) => ShaderMask(
        blendMode: BlendMode.srcATop,
        shaderCallback: (rect) => LinearGradient(
          begin: Alignment(-1 + _c.value * 2.4, -.4),
          end: Alignment(-.4 + _c.value * 2.4, .4),
          colors: [FC.surface, FC.surface2, FC.surface],
          stops: const [.15, .5, .85],
        ).createShader(rect),
        child: child,
      ),
      child: widget.child,
    );
  }
}

/// Dark block used as a placeholder before an image decodes.
class SkeletonBox extends StatelessWidget {
  final double? width;
  final double? height;
  final BorderRadius borderRadius;
  const SkeletonBox({super.key, this.width, this.height, this.borderRadius = const BorderRadius.all(Radius.circular(10))});

  @override
  Widget build(BuildContext context) => Shimmer(
        child: Container(
          width: width,
          height: height,
          decoration: BoxDecoration(color: FC.surface2, borderRadius: borderRadius),
        ),
      );
}

/// Image with a shimmering placeholder and a graceful failure state.
class AppImage extends StatelessWidget {
  final String asset;
  final BoxFit fit;
  final Alignment alignment;
  final double? width;
  final double? height;
  const AppImage(this.asset, {super.key, this.fit = BoxFit.cover, this.alignment = Alignment.center, this.width, this.height});

  @override
  Widget build(BuildContext context) => Image.asset(
        asset,
        fit: fit,
        alignment: alignment,
        width: width,
        height: height,
        frameBuilder: (context, child, frame, wasSync) {
          if (wasSync || frame != null) {
            return AnimatedOpacity(
              opacity: 1,
              duration: Motion.slow,
              child: child,
            );
          }
          return Shimmer(child: Container(width: width, height: height, color: FC.surface2));
        },
        errorBuilder: (context, _, __) => Container(
          width: width,
          height: height,
          alignment: Alignment.center,
          color: FC.surface2,
          child: Ic(IconName.fuel, size: 18, color: FC.dim),
        ),
      );
}

// ---------------------------------------------------------------------------
// AnimatedProgress — eases to every new value instead of jumping
// ---------------------------------------------------------------------------
class AnimatedProgress extends StatelessWidget {
  final double value; // 0..1
  final double height;
  final Color? color;
  final Duration duration;
  const AnimatedProgress(this.value, {super.key, this.height = 6, this.color, this.duration = Motion.slow});

  @override
  Widget build(BuildContext context) => ClipRRect(
        borderRadius: BorderRadius.circular(height),
        child: TweenAnimationBuilder<double>(
          tween: Tween(begin: 0, end: value.clamp(0.0, 1.0)),
          duration: duration,
          curve: Motion.soft,
          builder: (context, v, _) => LinearProgressIndicator(
            value: v,
            minHeight: height,
            backgroundColor: FC.line,
            valueColor: AlwaysStoppedAnimation(color ?? FC.gold),
          ),
        ),
      );
}

// ---------------------------------------------------------------------------
// Page transition used by the shell
// ---------------------------------------------------------------------------
class PageSwap extends StatelessWidget {
  final Animation<double> animation;
  final Widget child;
  const PageSwap({super.key, required this.animation, required this.child});

  @override
  Widget build(BuildContext context) {
    final t = CurvedAnimation(parent: animation, curve: Motion.soft);
    return FadeTransition(
      opacity: t,
      child: SlideTransition(
        position: Tween(begin: const Offset(0, .035), end: Offset.zero).animate(t),
        child: ScaleTransition(scale: Tween(begin: .985, end: 1.0).animate(t), child: child),
      ),
    );
  }
}

/// Small geometric "bling" used behind hero art (slow rotating ring).
class SlowSpin extends StatefulWidget {
  final Widget child;
  final Duration period;
  const SlowSpin({super.key, required this.child, this.period = const Duration(seconds: 26)});

  @override
  State<SlowSpin> createState() => _SlowSpinState();
}

class _SlowSpinState extends State<SlowSpin> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(vsync: this, duration: widget.period)..repeat();

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
        animation: _c,
        builder: (context, child) => Transform.rotate(angle: _c.value * 2 * math.pi, child: child),
        child: widget.child,
      );
}