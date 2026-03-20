import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// Dual-mode barcode scanner widget.
///
/// Mode 1 (USB HID): Invisible TextField that captures keyboard input from USB
/// barcode scanners. Accumulates keystrokes until Enter (scanner delimiter).
///
/// Mode 2 (Camera): Placeholder for mobile_scanner integration. Activated by
/// tapping the barcode icon button. For now shows a manual entry dialog.
class BarcodeScannerField extends StatefulWidget {
  final ValueChanged<String> onScanned;
  final String? hintText;

  const BarcodeScannerField({
    super.key,
    required this.onScanned,
    this.hintText,
  });

  @override
  State<BarcodeScannerField> createState() => _BarcodeScannerFieldState();
}

class _BarcodeScannerFieldState extends State<BarcodeScannerField> {
  final _controller = TextEditingController();
  final _focusNode = FocusNode();
  bool _scanSuccess = false;

  @override
  void initState() {
    super.initState();
    // Auto-focus for USB scanner input
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _focusNode.requestFocus();
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  void _handleSubmit(String value) {
    final barcode = value.trim();
    if (barcode.isNotEmpty) {
      widget.onScanned(barcode);
      _controller.clear();
      setState(() => _scanSuccess = true);
      Future.delayed(const Duration(milliseconds: 800), () {
        if (mounted) setState(() => _scanSuccess = false);
      });
    }
    // Re-focus for next scan
    _focusNode.requestFocus();
  }

  void _showManualEntry() {
    final manualController = TextEditingController();
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Barcode'),
        content: TextField(
          controller: manualController,
          autofocus: true,
          decoration: const InputDecoration(
            hintText: 'Enter barcode manually',
            border: OutlineInputBorder(),
          ),
          onSubmitted: (value) {
            Navigator.of(ctx).pop();
            _handleSubmit(value);
          },
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () {
              Navigator.of(ctx).pop();
              _handleSubmit(manualController.text);
            },
            child: const Text('OK'),
          ),
        ],
      ),
    ).then((_) {
      manualController.dispose();
      _focusNode.requestFocus();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        // Invisible text field for USB scanner HID input
        Expanded(
          child: SizedBox(
            height: 48,
            child: TextField(
              controller: _controller,
              focusNode: _focusNode,
              onSubmitted: _handleSubmit,
              decoration: InputDecoration(
                hintText: widget.hintText ?? 'Scan barcode...',
                prefixIcon: AnimatedSwitcher(
                  duration: const Duration(milliseconds: 300),
                  child: Icon(
                    Icons.qr_code_scanner,
                    key: ValueKey(_scanSuccess),
                    color: _scanSuccess ? Colors.green : null,
                  ),
                ),
                border: const OutlineInputBorder(),
                contentPadding: const EdgeInsets.symmetric(horizontal: 12),
              ),
              inputFormatters: [
                FilteringTextInputFormatter.deny(RegExp(r'\n')),
              ],
            ),
          ),
        ),
        const SizedBox(width: 8),
        // Camera/manual entry button
        IconButton.filled(
          onPressed: _showManualEntry,
          icon: const Icon(Icons.camera_alt),
          tooltip: 'Camera / Manual entry',
        ),
      ],
    );
  }
}
