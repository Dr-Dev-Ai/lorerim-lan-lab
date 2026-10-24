# Sync Health panel

Read-only in-game timing and connection diagnostics. Default: compact while
connected. F10 cycles compact, detailed, hidden. It does not capture mouse input.
Optional settings: `Data/SKSE/Plugins/LoreRimSyncHealth.ini`; see the template.
Position, scale, initial mode and toggle key apply at startup.

The panel samples ECS/network state on UpdateEvent at most five times per second
and renders a mutex-protected copy. Graphs keep 120 one-second samples. Only the
five oldest remote actor streams are retained for display. Rendering never
queries the ECS or calls actor movement functions. Interpolation diagnostics
observe existing decisions without changing playback/correction behavior.

- Ping and connection quality come from GameNetworkingSockets. Quality is
  in-order delivery success, not a precise packet-loss counter.
- Queue time and pending/unacknowledged reliable bytes describe local sending.
- Actor age uses the networking receive clock, not a comparison between owner
  and receiver clocks. Jitter/buffer use the existing per-actor playback clock.
  Streams older than max(1000 ms, six snapshot intervals) are marked stale.
  Zero remote samples can be normal on a server with one player.
- Correction/snap totals cover currently monitored actors; totals may decrease
  when actors unload or ownership changes. Teleports are excluded. Corrections
  smaller than one game unit are not counted. Game units are not metres.
- Update age can continue increasing in the rendering callback while game
  updates stop. Update gaps above 250 ms also include expected loads and rests.
- Time-of-day difference is an estimate against the last server calendar
  report, advanced using its time scale and half the current ping. It is shown
  after five seconds of settling. It does not compare calendar dates or prove
  that the server clock is correct. Paired checkpoints and transitions may
  legitimately change this estimate.
- An online save load is logged and now closes the connection at the completed
  load event, with a HUD explanation. A persistent disconnected notice remains
  in the panel until reconnect, including when telemetry display is set to off.
  No stale connection metrics are shown in that notice. It does not roll back the server or peers
  to the save's inventory/quest state. Disconnect BEFORE loading and
  use a save consistent with party progress before reconnecting. Campaign mode
  additionally invalidates admission on load. The post-load disconnect is a
  fallback boundary, not a transactional preload barrier or universal repair.

Amber highlights timing/risk indicators, not a measured desync percentage.
Server processing time and quest/inventory agreement are explicitly unmeasured.
No new messages, protocol identity, server deployment or third-party plugin.
True state comparisons and server processing telemetry require further work.

Validation: native client compilation passed. Host runtime visibility and F10 compact/details/hidden modes passed. Detailed
view was visually inspected: local ping0 ms, quality100%/100%, queue0 ms,
pending reliable0 bytes, clock estimate+1.1 game seconds and client update4.8 ms.
Two locally owned actors and no remote streams were present. Remote actor
measurements and two-client behavior remain untested; the connected-load warning
was not deliberately induced.
No new gameplay unit tests were added. Existing source-level engine accessors
are reused; no new binary patch, vtable slot or raw engine offset is introduced.
