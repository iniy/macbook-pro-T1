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
| Esc / Fn / F1–F12 / volume / media / brightness | Existing T1Bridge IPC and desktop helper, symbolic control icons | Protocol/scene tests and physical frame submission pass; individual controls pending |
| Fingerprint prompts and cancellation | Existing public overlay and typed cancellation | Priority tests; physical acceptance pending |
| Lock / blank display | Hide application actions; blank panel with display | Scene tests; real-session acceptance pending |
| Rich app widgets, text suggestions, scrubbing | Not implemented | Requires app-specific integration |
| GNOME versions other than 51 | Not enabled | Adapter review required |

## Install

Requires the working T1Bridge configuration-2 installation from this repository,
GNOME Shell 51, Python 3, PyGObject, Cairo/Pango 1.56+ and AT-SPI. Install any missing
runtime dependencies through Ubuntu's package manager:

```bash
sudo apt install python3-gi python3-cairo python3-gi-cairo gir1.2-atspi-2.0 gir1.2-pango-1.0
python3 touchbar/install.py install
python3 touchbar/install.py enable
```

Run the two Python commands as the desktop user. Installation copies files to
`~/.local/lib/macbook-t1-gnome-touchbar` and the GNOME user extension directory.
Enable preserves any existing selected renderer, selects the bridge, and enables
the extension. If GNOME has not discovered the new extension yet, log out and
back in after saving your work. The installer leaves the running Touch Bar alone
until the extension is available. No reboot or fingerprint re-enrollment is needed.

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
application dialog, notification banner, app profile, and default controls.
Controls with more than five contextual actions have a page button. The actual
GNOME/app button labels are shown, including localization. Every action requires
a deliberate tap and release on a stable layout. A drag, multiple fingers or a
context change cancels the pending tap.

Confirmations show only their own buttons, centered on the strip. A standard
Restart confirmation has Cancel and Restart; Power Off has Cancel and Power Off.
The strip uses the original T1Bridge control glyphs and grouped layout, lowercase
`esc`, rounded charcoal key plates, a blue primary action and a pressed highlight.
Inter Regular/Medium 4.1 is bundled and loaded only inside the renderer. Labels
use absolute panel pixels so desktop DPI or theme changes cannot resize them.
App controls share the same single-row styling, with Esc and volume staying in
their usual positions. Holding Fn temporarily displays the function keys.
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
gjs -m tests/touchbar/test-state.js
python3 tests/touchbar/gnome-integration.py
```

The Python and GJS tests cover gesture cancellation, stale actions, sensitivity,
replay, pagination, context priority, malformed wire messages, buffer ownership,
installer restoration and cold-process GI/Cairo startup. The cold-start test also
uses service-relative input timestamps to exercise a full tap through the renderer.

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
