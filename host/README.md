# Desktop host

This directory will contain the shared host/session runtime plus native platform adapters.

```text
host/
  shared/     protocol/session orchestration
  windows/    Windows Graphics Capture + Windows input/audio adapters
  linux/      PipeWire/portal and X11 compatibility adapters
```

The platform layer must expose capabilities at runtime. In particular, Linux/Wayland environments differ in what capture and remote-input mechanisms the compositor permits.

V0 development order is Windows real capture first, then Linux/Arch against the same protocol. A deterministic fake capture source should remain available for tests and Android development.
