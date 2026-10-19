# GNOME desktop preferences

`./desktop/configure.sh` applies the requested settings to the desktop user,
including when called through `sudo ./install.sh`:

* Report `disable-while-typing`, `tap-to-click` and `tap-and-drag` under
  `org.gnome.desktop.peripherals.touchpad`. These were requested as **get**
  commands and are not changed.
* Set `org.gnome.desktop.a11y.keyboard bouncekeys-delay` to `100`.
* Set `org.gnome.desktop.a11y.keyboard bouncekeys-enable` to `true`.

The script uses the logged-in user's session rather than root's dconf database.
Original keyboard values are saved once under
`~/.local/state/macbook-pro-T1/desktop/before.json`. Re-running is idempotent.

```bash
./desktop/configure.sh --show
./desktop/configure.sh --restore
```

Restore changes only fields that still match the script's installed values,
preserving later user edits. The one-shot installer's `--no-desktop` option skips
this step for headless use.
