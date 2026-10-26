# GNOME-aware T1 Touch Bar

A per-user renderer and GNOME Shell 51 extension for the existing T1Bridge stack.
It mirrors GNOME confirmation buttons and notification actions, discovers
accessible application dialog buttons, and switches shortcut profiles with focus.

See [detailed research and design](RESEARCH.md). This is an initial implementation,
not a claim of complete macOS feature parity or universal application support.

## Coverage

| Area | Implementation | Acceptance |
| --- | --- | --- |
| Shutdown / restart / logout confirmations | Actual GNOME buttons and callbacks | Isolated GNOME 51 tests pass; physical Power Off dialog and Cancel confirmed |
| Other GNOME ModalDialog confirmations | Top dialog, visible/enabled buttons | Same adapter; individual dialogs need acceptance |
| Notification banner actions | Actual GNOME actions and Dismiss | Isolated GNOME action invocation passes |
| GTK / libadwaita application dialogs | AT-SPI semantic button actions | GTK4 / Adw.AlertDialog fixtures pass, including disabled buttons and stale focus |
| Browser, VS Code, Terminal, Files | Fixed app-specific shortcuts | Profile mappings implemented; app acceptance pending |
| Browser / desktop video playback | Focused-player MPRIS play/pause, ±10 seconds, draggable timeline | Firefox / Chrome / VLC private-bus tests pass; player capabilities vary |
| Live video mirroring | Disabled; no direct hardware video path is available in this renderer | Desktop capture prototypes were retired after excessive CPU use |
| Firefox YouTube thumbnail filmstrip | Public storyboard frames in the existing seek area | Real video frames rendered; asynchronous loading, track changes and seek mapping tested |
| Esc / Fn / F1–F12 / volume / media / brightness | Existing T1Bridge IPC and desktop helper, symbolic control icons | Protocol/scene tests and physical frame submission pass; individual controls pending |
| Fingerprint prompts and cancellation | Existing public overlay and typed cancellation | Priority tests; physical acceptance pending |
| Lock / blank display | Hide application actions; blank panel with display | Scene tests; real-session acceptance pending |
| Rich app widgets, text suggestions, filmstrips on other sites | Not implemented | Requires app-specific integration |
| GNOME versions other than 51 | Not enabled | Adapter review required |

## Install

Requires the working T1Bridge configuration-2 installation from this repository,
GNOME Shell 51, Python 3, PyGObject, Pillow, Cairo/Pango 1.56+, AT-SPI. Install any missing
runtime dependencies through Ubuntu's package manager:

```bash
sudo apt install python3-gi python3-cairo python3-gi-cairo python3-pil gir1.2-atspi-2.0 gir1.2-pango-1.0
python3 touchbar/install.py install
python3 touchbar/install.py enable
```

Run the two Python commands as the desktop user. Installation copies files to
`~/.local/lib/macbook-t1-gnome-touchbar` and the GNOME user extension directory.
Enable preserves any existing selected renderer, selects the bridge, and enables
the extension. Native dialog event registration uses standard toolkit accessibility;
the previous setting is recorded and restored on disable/uninstall. It does not
enable a screen reader. If GNOME has not discovered the new extension yet, log out and
back in after saving your work. The installer leaves the running Touch Bar alone
until the extension is available. No reboot or fingerprint re-enrollment is needed.

The optional audio visualizer also uses `gir1.2-gstreamer-1.0`,
`gstreamer1.0-plugins-good`, and `pulseaudio-utils` (normally installed on this
desktop). If unavailable, playback controls still work and the visualizer rests.

```bash
python3 touchbar/install.py status
python3 touchbar/bridge.py --check
python3 touchbar/bridge.py --preview /tmp/touchbar-preview.png
```

The component is packaged with this repository but remains a separate opt-in
installation while acceptance is incomplete. The one-shot hardware installer
continues selecting the proven built-in renderer by default.

## Operation

Priority is display-off blanking, Touch ID, held-Fn keys, GNOME shell modal,
application dialog, notification banner, media playback, app profile, and default controls.
Controls with more than five contextual actions have a page button. The actual
GNOME/app button labels are shown, including localization. Every action requires
a deliberate tap and release on a stable layout. A drag, multiple fingers or a
context change cancels the pending tap.

When a focused browser or video player exposes playing or paused media over
MPRIS, its shortcut area becomes a playback strip. Supported application families
include Firefox, Chromium/Chrome, Brave, Vivaldi, GNOME Web, VLC, mpv/Celluloid,
Totem/Showtime, Haruna, SMPlayer and Parole. Other MPRIS players are eligible
when they advertise a recognizable video file URI. The strip has
play/pause beside the timeline, elapsed/remaining time and a draggable
timeline. Dragging previews the target time and releasing commits one seek.
Progress updates do not interrupt a held touch. The strip remains available
while paused and returns to app shortcuts when the player disappears or stops.

Only MPRIS players owned by the focused application process are eligible. Commands
recheck focus, player ownership and track identity; absolute seeks include the
current track ID. Firefox Snap access uses the existing unconfined user service.
No browser extension, injected page scripts, debug port or per-site setup is needed.
Firefox controls also require the media title to match the active tab's window
caption. A different tab gets the usual browser shortcuts, even while another
tab keeps playing. Returning to the video restores its cached timing and
thumbnails. The caption comes from the already discovered active accessibility
window; browser documents are never scanned. Only a normalized title hash is
kept in the snapshot, and queued seeks recheck the tab before execution. Sites
whose media title cannot be matched to the tab retain browser shortcuts.
Other browsers select their active media session, which may contain audio or video;
MPRIS itself does not identify the focused tab or supply thumbnail frames. Websites
that omit duration show an unavailable timeline; play/pause remains available
according to the player's advertised capabilities. A player that cannot seek
gets a disabled timeline.

The former ten-second seek buttons are replaced by a noninteractive, sixteen-bar
audio spectrum, colored from cyan through green and yellow to red. Play/pause
sits immediately beside the unchanged timeline; this layout stays stable while
paused. The bars respond to the current output mix
(including other audible apps), using GStreamer's native FFT on a 16 kHz mono
sink monitor at 25 updates per second. Audio is neither saved nor sent anywhere,
and the microphone is never selected. The analyzer closes its stream when video
controls are hidden, paused, muted, or covered by Fn, volume, or Touch ID controls.
Existing mixer events follow output-device changes without extra idle polling.
Silence or an unavailable backend leaves resting bars. Audio-only changes repaint
just the visualizer; timeline motion and glass-lens behavior keep their existing
cadence. Missing audio services/plugins retry with backoff without blocking input.

For an already identified video, the adapter retains its known duration if
Firefox drops or zeros that field after seeking or a focus change. It follows `Seeked` notifications and
the playback clock when Firefox incorrectly reports position zero
([Mozilla bug 2065930](https://bugzilla.mozilla.org/show_bug.cgi?id=2065930)).
The cache is limited to the same player and media identity, including a private
hash of stable track metadata, so a reused track path cannot inherit another
video's timing. If Firefox reports zero before any seek notification, the
same-video playback clock continues between polls instead of restarting at zero.
Real seek notifications, including a seek to the beginning, remain authoritative.
A different video or stopped player clears the active timing, including when a
previously played video is opened again. Recovery uses the existing polls and
does not add browser scanning or playback commands.

For public YouTube videos with storyboards, twelve wider preview frames with
eight-pixel gaps replace the plain timeline rail. A raised glass lens magnifies
the selected frame, with a light rim, soft shadow and reflective highlights; elapsed and
remaining time, playback controls and seek touch mapping retain their positions.
The marker animates at up to 60 Hz, eases between touch samples and keeps its
preview position while the browser confirms a released seek. Coarse browser
position samples are corrected gradually instead of stepping backwards. The
lens reuses up to 240 frames from the same downloaded sprites and dissolves
between them over 100 ms; the twelve visible tiles and their spacing stay fixed.
These are storyboard previews, rather than a decoded live video feed.
The page's public storyboard is fetched without browser cookies, an extension,
audio/video downloads or changes to browser settings. Only canonical YouTube
watch pages and their `i.ytimg.com` storyboard images are requested.

A separate worker loads a bounded number of sprite images into a two-video
memory cache. Focus changes cancel unfinished work without marking the video as
unavailable, so returning can retry immediately. URLs, titles, video IDs and thumbnail images are not written by
the renderer to disk or diagnostics. Loading, failures, unavailable/private/live
videos and sites without a storyboard adapter retain the time scrubber. A
duration mismatch suppresses images, so an ad does not reuse a different video's
filmstrip. Thumbnail arrival redraws paused playback without changing gesture
identity or sending a media command.

Live video mirroring is disabled. The desktop capture and browser geometry
prototypes exceeded 20 fps but caused excessive CPU load and affected playback.
They have been removed rather than kept as a background fallback. Chrome keeps
basic playback controls and the time bar, with no thumbnails, frame capture,
browser helper, or video-specific accessibility scanning. Firefox retains the
approved storyboard filmstrip, glass lens, spacing, and seek actions.

For energy efficiency, passive progress redraws only when a time label or a
quarter-pixel marker step changes. Dragging and the existing 100 ms lens dissolve
retain their 60 Hz animation cadence. An unchanged or unavailable timeline cannot
cause a 1 ms polling loop. Dialog discovery caches a confirmed absence for up to
one second, invalidating immediately on focused-window, modal or child-tree
events; active dialogs and action guards still receive fresh checks.

Confirmations show only their own buttons, centered on the strip. A standard
Restart confirmation has Cancel and Restart; Power Off has Cancel and Power Off.
The strip uses the original T1Bridge control glyphs and grouped layout, lowercase
`esc`, rounded charcoal key plates, a blue primary action and a pressed highlight.
Inter Regular/Medium 4.1 is bundled and loaded only inside the renderer. Labels
use absolute panel pixels so desktop DPI or theme changes cannot resize them.
App controls share the same single-row styling, with Esc and volume staying in
their usual positions. Holding Fn temporarily displays the function keys.
Short taps on the volume speaker buttons lower or raise volume by 5%. Holding
either button for 350 ms opens a compact slider beside that button, with a blue
filled track, white thumb and circular × close control. Its appearance follows
Apple's [Touch Bar volume reference](https://support.apple.com/en-hk/guide/macbook-pro/apd2ef3d66b2/2023/mac/14),
with placement anchored to the opening finger and clamped to the right edge.
Drag its thumb to adjust volume, then tap × to restore the usual controls. You
can also hold a speaker button, slide left or right without lifting, and release
to return immediately. That gesture starts at the current level, so opening the
popover never jumps the volume to the finger's absolute position. App changes,
dialogs, Touch ID and Fn also dismiss the popover. Volume stays in
the 0–100% range; dragging above zero unmutes the output. The mute button turns
red when the default output is muted and returns to normal when unmuted,
including changes made from desktop sound settings. Mixer calls run off the
rendering thread and coalesce drag samples at up to 20 updates per second.
An idle `pactl subscribe` connection reports output changes without polling.
Without `pactl` (provided by `pulseaudio-utils`), the renderer falls back to
checking every two seconds while volume controls are visible. Hidden controls
do not poll. `wpctl`, supplied by WirePlumber, performs the mixer operations.
Browser and Files (Nautilus) shortcuts use monochrome icons for navigation,
reload, new tab, search, address, and new folder. An ellipsis opens the next
page of browser controls. Their shortcuts, order, and touch targets are unchanged.

Active Touch ID guidance sits at the right edge beside the sensor, with an arrow
pointing toward it and the original renderer's 150 ms fade-in. The existing
Cancel button is at the far left. Animation frames keep touch targets stable
and stop once the fade completes.

This is a macOS-like visual treatment, not Apple's exact San Francisco font or
proprietary artwork. [Apple's font license](https://developer.apple.com/fonts/)
does not grant this Linux use. [Asset provenance and licenses](assets/README.md)
cover the included Inter, Cupertino and Myna UI assets.

System confirmations use the real GNOME button; the bridge never initiates a
shutdown itself. Application dialogs use AT-SPI actions, not guessed Enter/Esc
bindings. Screen lock hides application context. The stock fingerprint backend,
password authentication and resume hooks are not modified.

## Recovery / removal

```bash
python3 touchbar/install.py disable
python3 touchbar/install.py uninstall
```

Disable restores the previously selected renderer and restarts the user renderer
service. Uninstall also removes unchanged files owned by this installer. Local
edits and a later user-selected renderer are preserved rather than overwritten.
If the custom renderer exits, T1Bridge automatically starts its built-in renderer.
If only the GNOME extension disappears, app controls are withdrawn and hardware
controls remain available. Inspect service errors with:

```bash
journalctl --user -u t1-touchbar.service -b
```

The bridge does not log window titles, button text, notification bodies, typed
content or biometric state. Read-only diagnostic output reports only component
availability, context type and action count.

## Tests

```bash
python3 -m unittest discover -s tests -p test_touchbar_bridge.py -v
python3 -m unittest discover -s tests -p test_touchbar_media.py -v
python3 -m unittest discover -s tests -p test_touchbar_thumbnails.py -v
python3 -m unittest discover -s tests -p test_touchbar_motion.py -v
python3 -m unittest discover -s tests -p test_touchbar_volume.py -v
gjs -m tests/touchbar/test-state.js
python3 tests/touchbar/gnome-integration.py
```

The Python and GJS tests cover gesture cancellation, stale actions, sensitivity,
replay, pagination, context priority, malformed wire messages, buffer ownership,
installer restoration and cold-process GI/Cairo startup. The cold-start test also
uses service-relative input timestamps to exercise a full tap through the renderer.
Media tests additionally cover typed MPRIS calls on an isolated D-Bus, matching
the focused media process, stale-track/focus rejection, stream capabilities,
clock updates during dragging and single-seek release behavior. The private-bus
fixture also reproduces Firefox's zero-position/missing-duration bug, verifies
repeated seeks and external seek notifications, and checks reused track paths.
Thumbnail tests cover exact frame selection from shared sprites, short final
sprites, wrong-video rejection, nonblocking loading, superseded downloads,
duration mismatches, unchanged seek mapping and redraws while paused.
Motion tests cover coarse playback clocks, frame cadence, eased dragging, exact
release targets, delayed/rejected seeks, and continuous frame dissolves.

The integration runner starts a private D-Bus session and headless GNOME 51 with
temporary data directories. It checks real end-session Cancel callbacks,
notification ActionInvoked delivery, and GTK4/libadwaita dialog actions. It never
confirms shutdown, restart or logout. Additional test dependencies are `gjs`,
`gnome-shell`, `dbus-run-session`, `gir1.2-gtk-4.0` and `gir1.2-adw-1`.

Physical evidence on 26 October 2026: the installed service negotiated a
2170 × 60 panel and acknowledged/released a rendered frame. The user confirmed
that the actual GNOME Power Off buttons appeared and Cancel closed the dialog.
The later compact confirmation and icon layouts were inspected as full-width
PNG previews before installation. Post-sleep behavior with this renderer and
individual app profiles still need physical acceptance.
