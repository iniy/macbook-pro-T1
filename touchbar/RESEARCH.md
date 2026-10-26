# GNOME Touch Bar integration research

Research date: 26 October 2026. Implementation target: GNOME Shell 51.0,
Ubuntu 26.10, Wayland, and the existing T1Bridge hardware IPC v1 installation.
This is a desktop integration project, not a replacement fingerprint driver.

## What macOS parity means

Apple's NSTouchBar is an application framework: applications and the system
provide context-specific items. It is not a universal screen-to-button converter.
A useful Linux equivalent must combine several sources of context: the desktop
shell, application accessibility, application shortcuts, and explicit app APIs.
Matching a window title alone cannot determine whether a dialog's default button
means Save, Discard, Replace, or Delete.

The requested parity target includes automatic context changes, system
confirmations, application confirmations, notification actions, a normal control
strip, Fn keys, fingerprint prompts, and predictable recovery. Confirmations
temporarily replace the control strip with their own buttons, as requested.
It does not justify claiming universal app support before testing applications.

Primary reference: [Apple NSTouchBar](https://developer.apple.com/documentation/appkit/nstouchbar).

## 1. GNOME system confirmations

GNOME 51's EndSessionDialog inherits ModalDialog. Its shutdown, restart and
logout variants create Cancel and confirmation buttons through `addButton`.
Each button's existing callback performs the normal GNOME flow, including
closing the dialog and emitting its session-manager confirmation signal.
Alternative reboot actions and update-related labels can change dynamically.

The bridge inspects only the actor at the top of GNOME's modal stack, waits for
OPENED state, reads the actual mapped buttons, and preserves their ordering,
labels, sensitivity and default styling. A Touch Bar tap emits the existing
button's click signal. It never calls poweroff, reboot, login1, or a shell command
to implement a confirmation. Therefore GNOME remains responsible for inhibitors,
authentication, countdowns and session handling.

Unknown modal surfaces block app shortcuts instead of exposing actions belonging
to the window behind them. Nested dialogs supersede their parent. Hidden and
alternate buttons are not offered until GNOME displays them.

References: [EndSessionDialog 51.0](https://github.com/GNOME/gnome-shell/blob/51.0/js/ui/endSessionDialog.js),
[ModalDialog 51.0](https://github.com/GNOME/gnome-shell/blob/51.0/js/ui/modalDialog.js),
[Dialog 51.0](https://github.com/GNOME/gnome-shell/blob/51.0/js/ui/dialog.js),
[modal stack](https://github.com/GNOME/gnome-shell/blob/51.0/js/ui/main.js).

## 2. Notifications are a separate interface

The freedesktop notification protocol carries action IDs and localized labels.
It explicitly excludes modal message boxes. A notification watcher alone cannot
implement Save/Discard or shutdown confirmations.

GNOME's Notification objects own Action objects, with an `activate()` method.
Calling that method preserves GNOME's normal callback and resident-notification
behavior. The bridge mirrors actions only from the currently displayed banner,
plus a Dismiss control. It does not dump notification history or surface a hidden
notification while Do Not Disturb suppresses its banner. Inline text replies are
not implemented; the action may open the app's reply UI.

References: [notification specification 1.3](https://specifications.freedesktop.org/notification/latest-single/),
[GNOME Notification and Action](https://github.com/GNOME/gnome-shell/blob/51.0/js/ui/messageTray.js).

## 3. Application dialogs through AT-SPI

AT-SPI exposes accessible roles, names, states and semantic actions. A button's
Action interface can invoke its real click/press/activate action. This is more
precise than injecting Return into whichever window happens to be focused.

The reader matches GNOME's focused PID, looks only under an active application
window, and selects its visible dialog or modal accessible subtree. It mirrors
up to twelve named push buttons, including disabled buttons. Scans have node,
depth, per-call and elapsed-time budgets. No match, multiple ambiguous windows,
a stale object, a missing action, or timeout withdraws the dialog controls.

Entry fields, password fields and document contents are excluded from traversal.
There is no OCR, screenshot collection, keystroke recording or persisted window
history. Labels remain transient process/session-bus data.

Coverage depends on applications exposing correct accessibility semantics.
GTK/libadwaita dialogs are the first target; Electron/Chromium, Qt, sandboxed
portals, embedded web confirmations and custom-drawn dialogs require individual
acceptance tests. A background dialog is never activated just because its label
matches the displayed label.

References: [Accessible](https://gnome.pages.gitlab.gnome.org/at-spi2-core/libatspi/class.Accessible.html),
[Action invocation](https://gnome.pages.gitlab.gnome.org/at-spi2-core/libatspi/method.Action.do_action.html),
[accessible states](https://docs.gtk.org/atspi2/enum.StateType.html),
[GTK4 state export](https://github.com/GNOME/gtk/blob/4.20.2/gtk/a11y/gtkatspicontext.c).
GTK4 exports SENSITIVE for usable widgets without setting the older ENABLED bit;
requiring both would incorrectly disable real GTK4 dialog buttons.

## 4. Focus and application controls on Wayland

A GNOME Shell extension can use Shell.WindowTracker and the compositor's focused
window directly. This covers native Wayland windows as well as Xwayland windows.
The extension sends a stable window identity and a focus generation; a switch
away and back invalidates a pending tap even if the same app returns.

Initial fixed profiles cover browsers, VS Code/Codium, common terminals and
Files. The extension uses Mutter/Clutter's virtual keyboard for those explicit
shortcuts, releasing every pressed key in a finally block. No caller can submit
arbitrary keys or commands through the bridge API. These profiles are keyboard
shortcut mappings, not knowledge of application editor state.

Window Monitor Pro is useful prior art for focus notifications, but its published
GNOME version list stopped at 50 when checked. It does not expose dialog buttons.
The integrated extension targets 51 specifically and avoids a second dependency.

References: [WindowTracker](https://gnome.pages.gitlab.gnome.org/gnome-shell/shell/class.WindowTracker.html),
[GNOME 51 virtual keyboard](https://github.com/GNOME/gnome-shell/blob/51.0/js/ui/keyboard.js),
[Window Monitor Pro](https://extensions.gnome.org/extension/8549/window-monitor-pro/).

## 5. Existing T1Bridge is the hardware boundary

The installed hardware service already accepts complete pixel frames through
sealed memfd buffers and sends normalized touch/Fn events. Its typed actions
include Esc/F1–F12, panel/backlight changes and Touch ID cancellation. Arbitrary
Ctrl/Alt shortcuts are intentionally outside that privileged interface.

The new Python renderer runs as the logged-in user, connects to the existing
root-owned SOCK_SEQPACKET socket, verifies peer ownership, negotiates capabilities,
and respects frame ownership until FrameReleased. It neither opens DRM/hidraw
nor broadens uinput permissions. The existing launcher selects it through
`$XDG_CONFIG_HOME/t1bridge/renderer` and returns to its built-in renderer if the
selected process exits.

Fingerprint overlays read only the documented public cosmetic state file. Saved
fingerprints, the keybag, PAM and the sleep hooks are unchanged. The overlay
preempts desktop actions, and cancellation uses only the existing typed request.

Reference: [T1Bridge interfaces](https://github.com/standardagents/t1bridge/blob/main/docs/interfaces.md).

## 6. Action correctness and lifetime

The bridge's session-bus interface exports `GetState() -> JSON` and
`Activate(token, actionId) -> accepted`. An opaque instance/generation token binds
action IDs to the exact context. GNOME reconstructs the current context before
activation and consumes the token before calling the real action. Button identity,
label, sensitivity, modal identity and focus changes invalidate old tokens.

The renderer arms a scene only after a 300 ms settling period. It activates on
release after a 60 ms minimum contact, never on initial touch. Sliding to another
button, multiple contacts, a changed scene, a hold longer than five seconds,
out-of-order hardware events or a disconnected provider cancels the gesture. A timed-out
action is not retried because it might already have completed.

Hardware event timestamps are relative to the service's own start, not the host's
monotonic-clock epoch. The renderer checks their stream ordering and measures
tap duration using local receipt times. Comparing the two clock origins would
reject every valid tap. GI namespaces are initialized serially before starting
the desktop worker, preventing concurrent lazy imports from exposing incomplete
GLib overrides during startup.

Desktop calls run on a worker thread with bounded queues and timeouts; slow
application accessibility does not stop display rendering or fingerprint state.
The session bus is the existing per-user boundary. There is no network listener,
new root daemon, privilege escalation, authentication bypass or remote control API.

## 7. Compatibility and release limits

GNOME's modal stack and notification objects are private Shell APIs. They provide
the required integration depth but can change between Shell versions. Metadata
therefore enables version 51 only; future versions need an adapter review and
real-shell integration tests, not an untested metadata version bump.

Full macOS parity also includes app-authored rich sliders, candidate suggestions,
formatting palettes, color pickers, per-site thumbnail adapters and customizable layouts.
Those require application adapters and are not implemented by this generic dialog
bridge. The initial release targets the requested system/dialog workflow and a
small set of useful app profiles. A parity matrix in README records implemented
behavior separately from hardware acceptance and remaining app-specific work.

Browser playback now has a bounded MPRIS adapter, including play/pause,
ten-second skips and a time scrubber when the player supplies duration and
seeking. It matches the focused browser's process to the media bus owner and
uses track-aware `SetPosition` calls. Dynamic position samples are excluded from
gesture identity, so a moving timeline does not invalidate a drag. The
[MPRIS Player specification](https://specifications.freedesktop.org/mpris/latest/Player_Interface.html)
defines these capabilities and the stale-track protection; general thumbnail
extraction and per-tab video identification require browser-specific adapters.

Firefox's reported [MPRIS seek regression](https://bugzilla.mozilla.org/show_bug.cgi?id=2065930)
can zero the reported position and remove duration until playback is paused.
The adapter keeps known duration for the same media identity and anchors the
clock to `Seeked` notifications. Notifications are delivered through a private
GLib context drained on the desktop worker, which has no running GLib main loop.
Local observation also found continuous zero-position playing samples without
any `Seeked` notification. Firefox's same-video clock now continues from its
previous sample in that case, so polling cannot repeatedly rewind the lens to
the first second. Explicit seeks still override this fallback, and a new video
session discards old timing even when replaying a previously seen identity.
The identity also includes a hash of stable media metadata, because Firefox can
reuse its MPRIS track object path across videos. No media titles or URLs are
written to disk or diagnostics.

YouTube thumbnail support uses the public player's storyboard data. The adapter
validates the video ID, chooses a small sprite format, and samples twelve frames
across the video's duration. The storyboard specification and sprite layout are
also handled by the primary [yt-dlp YouTube extractor](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/youtube/_video.py).
The local implementation parses JSON without evaluating page scripts, allows
only YouTube's public page/image hosts, bounds image sizes and requests, and
fetches on a dedicated worker. It needs no browser settings or signing changes.
When data is missing or incompatible, the approved time scrubber remains active.

For smooth movement the renderer uses a 60 Hz animation deadline and a separate
presentation clock, so property polling and touch samples do not directly step
the marker. The lens reuses up to 240 previews from the already fetched sprites,
blending frame changes over 100 ms without adding network requests.

Live mirroring was prototyped through Mutter/PipeWire and reached about 30 fps,
but the combined browser accessibility queries, redraws and desktop capture cost
made real playback jitter. The user rejected that path. It is removed from the
renderer and installer; no browser capture helper is required or installed.
There is no direct decoder-to-Touch-Bar hardware video path in this implementation.
Chrome keeps basic MPRIS controls, while Firefox retains its approved storyboards.

Profiling identified repeated generic dialog scans and visually redundant 60 Hz
redraws as larger Python costs than the GStreamer capture thread itself. The
renderer now caches a verified absence of dialogs with native event invalidation,
skips passive progress redraws below quarter-pixel steps, and advances its frame
deadline even when duration is unavailable. Touch dragging and lens dissolves
retain the existing presentation clock and 60 Hz scheduling. A Rust rewrite is
not required to remove these avoidable operations.

The volume popover follows the compact capsule, blue track, broad white thumb,
and circular dismiss control illustrated in Apple's [MacBook Pro Essentials](https://support.apple.com/en-hk/guide/macbook-pro/apd2ef3d66b2/2023/mac/14).
Apple also documents [sliding directly on a Control Strip volume button](https://support.apple.com/en-lk/guide/mac-help/-mchlbfd5b039/mac).
Apple's [Logic Pro Touch Bar guide](https://support.apple.com/en-mz/guide/logicpro/lgcp94a1c475/mac)
also describes holding a level control, dragging its slider, and releasing to
return. The requested adapter interaction keeps 5% short taps and opens the
slider after a 350 ms hold; this delay is an implementation choice, not an
Apple-published timing. The compact slider follows the opening finger, with
edge clamping, rather than copying the example image's absolute coordinates.
A continuous hold-slide-release uses relative movement from the initial volume.
The normal controls return when the popover closes. Active mute uses a red plate,
as requested, with actual default-output state supplied by `wpctl` and refreshed
by PulseAudio-compatible sink/server events. No captured Apple bitmap is shipped
as an asset.
