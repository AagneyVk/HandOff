# V1 media pipeline contract

HandOff uses a GPU-first, bounded-latency media path. The media implementation must not grow an unbounded queue to preserve frames; stale frames are less valuable than current frames.

## Windows

Target a selected HWND with Windows Graphics Capture (`IGraphicsCaptureItemInterop::CreateForWindow`, Windows 10 1903+). Use a D3D11 device and a free-threaded capture frame pool so frame callbacks do not depend on a UI dispatcher. SDR V1 uses BGRA8; HDR must be detected and either tone-mapped or carried through an HDR-capable pipeline rather than silently clipping.

Capture callbacks do no blocking network work. A bounded latest-frame handoff feeds the encoder. Resize/content-size changes recreate the frame pool after outstanding frames are released. Window closure terminates the session cleanly.

Encoder preference: hardware H.264 low-latency profile, no B-frame/reordering dependency, frequent recoverable keyframes, explicit timestamps. Software fallback is allowed only when latency/CPU policy accepts it.

## Android

Decode H.264 with MediaCodec directly to a Surface. Prefer hardware codecs. On API 30+ enable low-latency decoding only when the selected codec advertises the low-latency feature. Never copy decoded video through application ByteBuffers merely to display it.

The render surface owns an explicit content transform. Touch coordinates are inverse-mapped through the same transform before they become normalized source-window coordinates.

## Transport rules

Control and media are logically separate. Control must remain responsive during video loss. Media packets carry session identity, sequence number, presentation timestamp, keyframe/config flags and bounded payload length. Corrupt/oversized packets are rejected. Decoder loss requests a new keyframe instead of waiting indefinitely.

V1 LAN target: prioritize interaction latency over perfect frame delivery. No unbounded retransmission queue for video.

## Release measurements

Record capture->encode, encode->send, network, receive->decode, decode->present, and input->visible-response latency separately. Also record dropped frames, queue depth, bitrate, FPS, decoder resets, reconnects and CPU/GPU load. A green build is not a streaming-performance pass.
