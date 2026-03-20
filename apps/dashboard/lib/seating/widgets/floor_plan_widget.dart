import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/floor_map.dart';
import '../models/office.dart';
import 'desk_pin_widget.dart';

/// Reusable floor plan viewer with interactive desk pins.
/// Supports pinch-to-zoom, pan, drag-to-place from tray, and drag-to-move pins.
class FloorPlanWidget extends StatefulWidget {
  final String? floorplanUrl;
  final List<DeskWithStatus> desks;
  final String? currentUserEmail;
  final void Function(DeskWithStatus desk)? onTapDesk;
  final void Function(double x, double y)? onTapEmpty;
  final void Function(DeskWithStatus desk, double x, double y)? onDeskMoved;
  final bool editMode;

  const FloorPlanWidget({
    super.key,
    this.floorplanUrl,
    required this.desks,
    this.currentUserEmail,
    this.onTapDesk,
    this.onTapEmpty,
    this.onDeskMoved,
    this.editMode = false,
  });

  @override
  State<FloorPlanWidget> createState() => _FloorPlanWidgetState();
}

class _FloorPlanWidgetState extends State<FloorPlanWidget> {
  final _transformController = TransformationController();
  final _imageKey = GlobalKey();

  // Track actual image rect within the container (BoxFit.contain may letterbox)
  Size _imageSize = Size.zero;
  Size _containerSize = Size.zero;

  @override
  void initState() {
    super.initState();
    _transformController.addListener(_onTransformChanged);
    _resolveImageSize();
  }

  @override
  void didUpdateWidget(covariant FloorPlanWidget oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.floorplanUrl != widget.floorplanUrl) {
      _imageSize = Size.zero;
      _resolveImageSize();
    }
  }

  @override
  void dispose() {
    _transformController.removeListener(_onTransformChanged);
    _transformController.dispose();
    super.dispose();
  }

  void _onTransformChanged() {
    // Rebuild to reposition pins when zoom/pan changes
    setState(() {});
  }

  /// Convert a global position to normalized (0-1) coordinates relative to the
  /// actual image area (accounting for BoxFit.contain letterboxing and zoom).
  ({double x, double y})? _globalToNormalized(Offset global) {
    final box = _imageKey.currentContext?.findRenderObject() as RenderBox?;
    if (box == null) return null;
    // Convert global to the InteractiveViewer child's local coords
    final local = box.globalToLocal(global);

    if (_containerSize == Size.zero) return null;

    // Calculate the actual image rect within the container (BoxFit.contain)
    final imageRect = _computeImageRect();
    if (imageRect == null) return null;

    final x = (local.dx - imageRect.left) / imageRect.width;
    final y = (local.dy - imageRect.top) / imageRect.height;
    return (x: x.clamp(0.0, 1.0), y: y.clamp(0.0, 1.0));
  }

  Rect? _computeImageRect() {
    if (_imageSize == Size.zero || _containerSize == Size.zero) return null;
    final scaleX = _containerSize.width / _imageSize.width;
    final scaleY = _containerSize.height / _imageSize.height;
    final scale = scaleX < scaleY ? scaleX : scaleY;
    final w = _imageSize.width * scale;
    final h = _imageSize.height * scale;
    final left = (_containerSize.width - w) / 2;
    final top = (_containerSize.height - h) / 2;
    return Rect.fromLTWH(left, top, w, h);
  }

  /// Convert normalized (0-1) coords to pixel offset within the container,
  /// accounting for zoom/pan transform.
  Offset _normalizedToLocal(double nx, double ny) {
    final rect = _computeImageRect();
    if (rect == null) return Offset(nx * _containerSize.width, ny * _containerSize.height);
    final untransformed = Offset(rect.left + nx * rect.width, rect.top + ny * rect.height);
    // Apply the InteractiveViewer's transform matrix
    return MatrixUtils.transformPoint(_transformController.value, untransformed);
  }

  @override
  Widget build(BuildContext context) {
    final positioned = widget.desks.where(
      (d) => d.desk.posX != null && d.desk.posY != null,
    ).toList();
    final unpositioned = widget.desks.where(
      (d) => d.desk.posX == null || d.desk.posY == null,
    ).toList();

    return Column(
      children: [
        // Unpositioned desk tray (edit mode only)
        if (widget.editMode && unpositioned.isNotEmpty)
          _UnpositionedTray(desks: unpositioned, onTapDesk: widget.onTapDesk),

        // Floor plan with zoom/pan and desk pins
        Expanded(
          child: LayoutBuilder(
            builder: (context, constraints) {
              _containerSize = Size(constraints.maxWidth, constraints.maxHeight);
              return ClipRect(
                child: DragTarget<DeskWithStatus>(
                  builder: (context, candidateData, rejectedData) {
                    return Stack(
                      children: [
                        // Zoomable/pannable floor plan (image only)
                        InteractiveViewer(
                          transformationController: _transformController,
                          minScale: 1.0,
                          maxScale: 5.0,
                          boundaryMargin: const EdgeInsets.all(100),
                          child: GestureDetector(
                            onTapDown: widget.editMode && widget.onTapEmpty != null
                                ? (details) {
                                    final norm = _globalToNormalized(details.globalPosition);
                                    if (norm != null) {
                                      widget.onTapEmpty!(norm.x, norm.y);
                                    }
                                  }
                                : null,
                            child: SizedBox(
                              key: _imageKey,
                              width: constraints.maxWidth,
                              height: constraints.maxHeight,
                              child: widget.floorplanUrl != null
                                  ? Image.network(
                                      widget.floorplanUrl!,
                                      fit: BoxFit.contain,
                                      errorBuilder: (_, __, ___) =>
                                          _placeholder(constraints),
                                      frameBuilder: (_, child, frame, loaded) {
                                        if (_imageSize == Size.zero) {
                                          WidgetsBinding.instance
                                              .addPostFrameCallback((_) {
                                            _resolveImageSize();
                                          });
                                        }
                                        return child;
                                      },
                                    )
                                  : _placeholder(constraints),
                            ),
                          ),
                        ),

                        // Desk pins — OUTSIDE InteractiveViewer to avoid gesture conflict
                        // Positions are transformed using the zoom/pan matrix
                        // Only render when image size is known (prevents position jump)
                        if (_imageSize != Size.zero || widget.floorplanUrl == null)
                          for (final ds in positioned)
                            _buildDeskPin(ds, constraints),

                        // Drop highlight overlay
                        if (candidateData.isNotEmpty)
                          Positioned.fill(
                            child: IgnorePointer(
                              child: Container(
                                color: Colors.blue.withValues(alpha: 0.1),
                              ),
                            ),
                          ),
                      ],
                    );
                  },
                  onAcceptWithDetails: widget.editMode
                      ? (details) {
                          final norm = _globalToNormalized(details.offset);
                          if (norm != null) {
                            widget.onDeskMoved?.call(
                              details.data,
                              norm.x,
                              norm.y,
                            );
                          }
                        }
                      : null,
                ),
              );
            },
          ),
        ),

        // Zoom controls
        if (widget.editMode)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                IconButton(
                  icon: const Icon(Icons.zoom_out, size: 20),
                  onPressed: () => _zoom(0.8),
                  tooltip: 'Zoom out',
                ),
                IconButton(
                  icon: const Icon(Icons.fit_screen, size: 20),
                  onPressed: _resetZoom,
                  tooltip: 'Fit',
                ),
                IconButton(
                  icon: const Icon(Icons.zoom_in, size: 20),
                  onPressed: () => _zoom(1.25),
                  tooltip: 'Zoom in',
                ),
              ],
            ),
          ),
      ],
    );
  }

  Widget _buildDeskPin(DeskWithStatus ds, BoxConstraints constraints) {
    final pos = _normalizedToLocal(ds.desk.posX!, ds.desk.posY!);
    const pinRadius = 10.0;

    if (widget.editMode && widget.onDeskMoved != null) {
      const hitSize = 40.0;
      return _DraggableDeskPin(
        key: ValueKey('pin-${ds.desk.id}'),
        deskStatus: ds,
        initialLeft: pos.dx - hitSize / 2,
        initialTop: pos.dy - hitSize / 2,
        imageKey: _imageKey,
        containerSize: _containerSize,
        computeImageRect: _computeImageRect,
        getTransform: () => _transformController.value,
        currentUserEmail: widget.currentUserEmail,
        onTapDesk: widget.onTapDesk,
        onMoved: (x, y) => widget.onDeskMoved!(ds, x, y),
      );
    }

    return Positioned(
      left: pos.dx - pinRadius,
      top: pos.dy - pinRadius,
      child: DeskPinWidget(
        deskStatus: ds,
        currentUserEmail: widget.currentUserEmail,
        onTap: widget.onTapDesk != null ? () => widget.onTapDesk!(ds) : null,
      ),
    );
  }

  void _resolveImageSize() {
    if (widget.floorplanUrl == null) return;
    final provider = NetworkImage(widget.floorplanUrl!);
    provider.resolve(ImageConfiguration.empty).addListener(
      ImageStreamListener((info, _) {
        if (mounted) {
          setState(() {
            _imageSize = Size(
              info.image.width.toDouble(),
              info.image.height.toDouble(),
            );
          });
        }
      }),
    );
  }

  void _zoom(double factor) {
    final current = _transformController.value.clone();
    final center = Offset(_containerSize.width / 2, _containerSize.height / 2);
    // Scale around center
    current.translate(center.dx, center.dy);
    current.scale(factor);
    current.translate(-center.dx, -center.dy);
    _transformController.value = current;
  }

  void _resetZoom() {
    _transformController.value = Matrix4.identity();
  }

  Widget _placeholder(BoxConstraints constraints) {
    return Container(
      width: constraints.maxWidth,
      height: constraints.maxHeight,
      color: Colors.grey.shade200,
      child: const Center(
        child: Icon(Icons.map_outlined, size: 64, color: Colors.grey),
      ),
    );
  }
}

/// Draggable desk pin for edit mode — drag to reposition on the floor plan.
/// Pins live OUTSIDE InteractiveViewer so pan gestures don't conflict.
class _DraggableDeskPin extends StatefulWidget {
  final DeskWithStatus deskStatus;
  final double initialLeft;
  final double initialTop;
  final GlobalKey imageKey;
  final Size containerSize;
  final Rect? Function() computeImageRect;
  final Matrix4 Function() getTransform;
  final String? currentUserEmail;
  final void Function(DeskWithStatus)? onTapDesk;
  final void Function(double x, double y) onMoved;

  const _DraggableDeskPin({
    super.key,
    required this.deskStatus,
    required this.initialLeft,
    required this.initialTop,
    required this.imageKey,
    required this.containerSize,
    required this.computeImageRect,
    required this.getTransform,
    required this.onMoved,
    this.currentUserEmail,
    this.onTapDesk,
  });

  @override
  State<_DraggableDeskPin> createState() => _DraggableDeskPinState();
}

class _DraggableDeskPinState extends State<_DraggableDeskPin> {
  late double _left;
  late double _top;
  bool _dragging = false;
  double _totalDragDistance = 0;
  late double _startLeft;
  late double _startTop;

  @override
  void initState() {
    super.initState();
    _left = widget.initialLeft;
    _top = widget.initialTop;
  }

  @override
  void didUpdateWidget(covariant _DraggableDeskPin oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!_dragging) {
      _left = widget.initialLeft;
      _top = widget.initialTop;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Positioned(
      left: _left,
      top: _top,
      child: SizedBox(
        width: 40,
        height: 40,
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onPanStart: (_) {
            _totalDragDistance = 0;
            _startLeft = _left;
            _startTop = _top;
          },
          onPanUpdate: (details) {
            _totalDragDistance += details.delta.distance;
            // Only start visual drag after moving > 8px (avoids accidental drag on tap)
            if (_totalDragDistance > 8) {
              if (!_dragging) {
                _dragging = true;
                HapticFeedback.mediumImpact();
              }
              setState(() {
                _left = (_left + details.delta.dx).clamp(
                  -10.0, widget.containerSize.width - 10);
                _top = (_top + details.delta.dy).clamp(
                  -10.0, widget.containerSize.height - 10);
              });
            }
          },
          onPanEnd: (_) {
            if (_dragging) {
              // Was a real drag — save new position
              setState(() => _dragging = false);
              final inv = Matrix4.tryInvert(widget.getTransform());
              final rect = widget.computeImageRect();
              if (rect != null && inv != null) {
                final screenPt = Offset(_left + 20, _top + 20);
                final localPt = MatrixUtils.transformPoint(inv, screenPt);
                final x = (localPt.dx - rect.left) / rect.width;
                final y = (localPt.dy - rect.top) / rect.height;
                widget.onMoved(x.clamp(0, 1), y.clamp(0, 1));
              }
            } else {
              // Was a tap (< 8px movement) — show desk info
              setState(() {
                _left = _startLeft;
                _top = _startTop;
              });
              widget.onTapDesk?.call(widget.deskStatus);
            }
          },
          child: Center(
            child: _dragging
                ? Transform.scale(
                    scale: 1.3,
                    child: DeskPinWidget(
                      deskStatus: widget.deskStatus,
                      currentUserEmail: widget.currentUserEmail,
                    ),
                  )
                : DeskPinWidget(
                    deskStatus: widget.deskStatus,
                    currentUserEmail: widget.currentUserEmail,
                  ),
          ),
        ),
      ),
    );
  }
}

/// Horizontal tray showing unpositioned desks that can be dragged onto the plan.
class _UnpositionedTray extends StatelessWidget {
  final List<DeskWithStatus> desks;
  final void Function(DeskWithStatus)? onTapDesk;

  const _UnpositionedTray({required this.desks, this.onTapDesk});

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 56,
      color: Colors.grey.shade100,
      child: Row(
        children: [
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 8),
            child: Icon(Icons.drag_indicator, size: 16, color: Colors.grey),
          ),
          Expanded(
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 8),
              itemCount: desks.length,
              separatorBuilder: (_, __) => const SizedBox(width: 4),
              itemBuilder: (context, index) {
                final ds = desks[index];
                final ext = ds.desk.deskExtension;
                final label = ext.length > 2 ? ext.substring(ext.length - 2) : ext;
                return Draggable<DeskWithStatus>(
                  data: ds,
                  feedback: Material(
                    color: Colors.transparent,
                    child: DeskPinWidget(deskStatus: ds),
                  ),
                  childWhenDragging: Opacity(
                    opacity: 0.3,
                    child: _chip(label),
                  ),
                  child: GestureDetector(
                    onTap: onTapDesk != null ? () => onTapDesk!(ds) : null,
                    child: _chip(label),
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _chip(String label) {
    return Chip(
      avatar: const Icon(Icons.desktop_mac, size: 14),
      label: Text(label, style: const TextStyle(fontSize: 12)),
      visualDensity: VisualDensity.compact,
      materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
    );
  }
}
