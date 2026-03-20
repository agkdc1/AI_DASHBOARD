// ignore: avoid_web_libraries_in_flutter
import 'dart:html' as html;

/// Redirect the current browser tab to the given URL.
void performWebRedirect(String url) {
  html.window.location.href = url;
}
