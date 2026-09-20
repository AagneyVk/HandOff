# RC9 physical-device compatibility

- Android 14+ now requests the entire default display, preventing partial-app capture coordinates from being applied to the physical phone screen.
- Accessibility gestures use the real default-display pixel size instead of app window metrics.
- Gestures are serialized so different Android frameworks cannot cancel a preceding tap or swipe when commands arrive close together.
- Every tap, drag and scroll reports completion or rejection back to the desktop viewer.
- The Android control setup screen distinguishes an enabled switch from a running service and provides manufacturer-aware setup and battery/background guidance.
- The desktop phone viewer starts at the source aspect ratio, remains freely resizable and has a Maximize/F11 control.
- The phone's desktop viewer no longer places keyboard/scroll/drag panels over the streamed content. A dedicated collapsible side rail owns its own space, and keyboard controls open only on request.
- Android instrumentation now enables the real accessibility service and verifies a platform gesture completes.
