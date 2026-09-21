# RC11 direct P2P

RC11 adds an optional, zero-cost Internet route without changing HandOff's media or control security model.

## Connection flow

1. The desktop listener starts on TCP 47821 as before.
2. A background worker discovers the local Internet gateway with SSDP.
3. When the gateway advertises UPnP WAN IP/PPP mapping, HandOff requests a temporary TCP mapping and verifies that the reported external IPv4 address is globally routable.
4. The pairing QR contains the LAN endpoint and, when available, the direct public endpoint. Both are covered by the same single-use pairing secret and certificate fingerprint.
5. Android tries LAN first, then the direct endpoint. Successful pairing stores both candidates in Android Keystore-encrypted credentials for later reconnects.
6. Each authenticated connection refreshes the saved direct candidate when the desktop advertises a newer one.
7. The mapping is renewed on the same external port while HandOff runs and removed on normal shutdown.

The router never decrypts the connection. Authentication, authorization, revocation, selected-window scoping and pinned TLS are identical on LAN and WAN.

## Why there is no signaling bill

The approach borrows the direct-ticket boundary from P2PShare: discovery data identifies a peer, while application data travels directly between devices. HandOff puts both candidates into the physical QR instead of maintaining a hosted signaling service. This preserves the download-and-pair UX without a user account, Tailscale, TURN or a metered relay.

## Honest network limits

Direct-only networking cannot guarantee universal reachability. RC11 reports LAN-only mode when there is no compatible UPnP gateway, the gateway is behind CGNAT, it has no global IPv4 address, or its mapping request is rejected. A public address can also change; a new QR refreshes the saved candidate. Solving those cases transparently requires a rendezvous/relay service or a managed overlay network and therefore cannot truthfully be promised as infrastructure-free.
