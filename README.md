# HandOff

HandOff is an experimental local-first continuity system for moving the **interaction surface** of a running application between devices without restarting the application or reconstructing its state from URLs.

The source device keeps executing the application. HandOff transports its live visual/audio output to another device and sends user input back to the source.

## V0 target

The first milestone is deliberately narrow:

1. Run a host on Windows or Arch Linux.
2. Discover the host from an Android device on the same LAN.
3. Select one desktop window.
4. Stream that window to Android with low latency.
5. Map Android tap/swipe input back to the selected source window.
6. Measure end-to-end and input-to-visible-response latency.

Audio and polished one-action handoff follow once the visual/input path is proven.

## Architecture

```text
                         HandOff Core
                    protocol / sessions
                    discovery / telemetry
                             |
              +--------------+--------------+
              |                             |
        Desktop host                    Android client
        +-----------+                  +-------------+
        |           |
     Windows      Linux
     backend      backend
```

The project intentionally separates shared session/protocol logic from OS-specific capture and input backends. Windows and Linux are first-class hosts rather than ports of one another.

## Product rule

HandOff is **not intended to become generic desktop mirroring**. The long-term abstraction is a detachable application surface: hand off one running activity, continue interacting with it elsewhere, then return to the source with the exact state preserved.

## Status

Bootstrap in progress. See `docs/ARCHITECTURE.md` and `docs/V0_PLAN.md`.
