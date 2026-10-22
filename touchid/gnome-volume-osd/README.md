# GNOME volume indicator for the attended T1 trial

The desktop provider changes PipeWire volume directly. GNOME Shell 51 does not
show its native OSD for those changes, and its `ShowOSD` D-Bus method restricts
callers. This optional user extension observes the current output's volume and
mute properties and displays the native Shell OSD. It never changes the volume,
sends keys, handles fingerprints, or participates in authentication.

The extension is inert without `t1bridge.trial=1`. It follows changes to the
default output, coalesces volume/mute notifications, suppresses initial-state
popups, and disconnects all handlers when disabled. Output changes from other
applications also show an indicator during trial boots. A command that leaves
volume and mute unchanged does not produce a new popup. GNOME 51 is the only
declared version; other versions require validation.

Install as the desktop user, never with sudo:

```sh
gnome-extensions pack touchid/gnome-volume-osd --out-dir /tmp
gnome-extensions install /tmp/macbook-t1-volume-osd@local.shell-extension.zip
```

GNOME discovers newly installed local extensions after signing out and back in.
Then enable with:

```sh
gnome-extensions enable macbook-t1-volume-osd@local
```

Installation is separate from the root-owned trial transaction. Remove this
optional user component independently, before or after trial rollback:

```sh
gnome-extensions disable macbook-t1-volume-osd@local
gnome-extensions uninstall macbook-t1-volume-osd@local
```

The one-boot trial's next reboot returns to the normal stack. Sign-out/sign-in
keeps the current trial boot, allowing the OSD test without rearming GRUB.
