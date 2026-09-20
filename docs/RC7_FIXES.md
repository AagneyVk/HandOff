# RC7 physical-device fixes

RC7 responds to physical Android and Windows testing:

- Desktop input now accepts the recently displayed frame while the next video frame is in flight. The old equality check rejected normal taps at streaming frame rates.
- Android identifies whether the HandOff accessibility service is installed and enabled, and explains that remote touch is special access rather than a normal app permission.
- The setup flow links directly to App info and Accessibility, including the Android 13+ **Allow restricted settings** step required for trusted sideloaded APKs.
- The computer viewer enters immersive mode and follows the stream orientation, giving landscape desktop streams substantially more usable space.
- Viewer controls are compact overlays; keyboard controls expand only when requested.
- A regression test covers touch input arriving while the following frame is already in flight.
