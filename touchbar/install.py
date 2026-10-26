#!/usr/bin/python3
# SPDX-License-Identifier: MIT
"""Install, select, inspect or remove the per-user GNOME Touch Bar bridge."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
UUID = 't1-gnome-bridge@local'


def atomic(path, data, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.t1-bridge-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(data)
        os.chmod(name, mode)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(*args):
    return subprocess.run(args, capture_output=True, text=True, check=False, timeout=10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('install', 'enable', 'disable', 'uninstall', 'status'))
    args = parser.parse_args()
    if os.geteuid() == 0:
        raise RuntimeError('Run as your desktop user, without sudo')
    home = Path.home()
    config = Path(os.environ.get('XDG_CONFIG_HOME', home / '.config'))
    data = Path(os.environ.get('XDG_DATA_HOME', home / '.local/share'))
    state = Path(os.environ.get('XDG_STATE_HOME', home / '.local/state')) / 'macbook-t1-gnome-touchbar'
    if not all(p.is_absolute() for p in (config, data, state)):
        raise RuntimeError('XDG paths must be absolute')
    library = home / '.local/lib/macbook-t1-gnome-touchbar'
    extension = data / 'gnome-shell/extensions' / UUID
    journal = state / 'install.json'
    selection = config / 't1bridge/renderer'
    previous = json.loads(journal.read_text()) if journal.exists() else {'files': {}}
    from gi.repository import Gio
    settings = Gio.Settings.new('org.gnome.shell')
    accessibility = Gio.Settings.new('org.gnome.desktop.interface')
    if args.action == 'status':
        print(run('gnome-extensions', 'info', UUID).stdout.strip())
        print('Renderer selected:', selection.exists() and not selection.is_symlink() and
              previous.get('selected_sha') == sha(selection))
        return
    if args.action == 'install':
        if not run('gnome-shell', '--version').stdout.startswith('GNOME Shell 51.'):
            raise RuntimeError('This adapter currently supports GNOME Shell 51 only')
        import gi
        gi.require_foreign('cairo')
        gi.require_version('Atspi', '2.0')
        gi.require_version('PangoCairo', '1.0')
        gi.require_version('Pango', '1.0')
        from gi.repository import Atspi, Pango, PangoCairo
        if not hasattr(PangoCairo.FontMap.get_default(), 'add_font_file'):
            raise RuntimeError('Bundled fonts require Pango 1.56 or newer')
        import cairo
        from PIL import Image
        payload = {library / p.name: p.read_bytes() for p in HERE.glob('*.py') if p.name != 'install.py'}
        payload.update({library / p.relative_to(HERE): p.read_bytes()
                        for p in (HERE / 'assets').rglob('*') if p.is_file()})
        payload.update({extension / p.name: p.read_bytes() for p in (HERE / 'gnome').glob('*') if p.is_file()})
        # Preflight every file before writing any of them.
        for path, contents in payload.items():
            if path.is_symlink():
                raise RuntimeError(f'Preserving existing symlink: {path}')
            if path.exists() and sha(path) not in (previous['files'].get(str(path)), hashlib.sha256(contents).hexdigest()):
                raise RuntimeError(f'Preserving locally modified file: {path}')
        for path, contents in payload.items():
            atomic(path, contents)
            previous['files'][str(path)] = hashlib.sha256(contents).hexdigest()
            atomic(journal, (json.dumps(previous, indent=2) + '\n').encode(), 0o600)
        print('Installed user files. Run enable to select the bridge.')
        return
    if args.action == 'enable':
        if not journal.exists():
            raise RuntimeError('Install the bridge first')
        if settings.get_boolean('disable-user-extensions') or UUID in settings.get_strv('disabled-extensions'):
            raise RuntimeError('The bridge is disabled in GNOME Extensions; enable it there first')
        if 'selection_before' not in previous:
            if selection.is_symlink():
                before = {'symlink': os.readlink(selection)}
            elif selection.exists():
                before = {'data': base64.b64encode(selection.read_bytes()).decode(),
                          'mode': selection.stat().st_mode & 0o777}
            else:
                before = None
            previous['selection_before'] = before
            previous['extension_before'] = UUID in settings.get_strv('enabled-extensions')
            atomic(journal, (json.dumps(previous, indent=2) + '\n').encode(), 0o600)
        launcher = ('#!/usr/bin/python3\nimport os\nos.execv("/usr/bin/python3", '
                    + repr(['/usr/bin/python3', str(library / 'bridge.py')]) + ')\n').encode()
        expected = previous.get('selected_sha')
        if expected and (selection.is_symlink() or not selection.exists() or sha(selection) != expected):
            raise RuntimeError('Renderer selection changed; preserving it')
        # Native dialog event registration can enable the standard AT-SPI bus.
        # Preserve the original setting for disable/uninstall.
        if 'accessibility_before' not in previous:
            previous['accessibility_before']=accessibility.get_boolean('toolkit-accessibility')
        enabled = list(settings.get_strv('enabled-extensions'))
        if UUID not in enabled:
            settings.set_strv('enabled-extensions', enabled + [UUID])
            Gio.Settings.sync()
        atomic(selection, launcher, 0o755)
        previous['selected_sha'] = hashlib.sha256(launcher).hexdigest()
        atomic(journal, (json.dumps(previous, indent=2) + '\n').encode(), 0o600)
        # A newly installed extension may need the next Wayland desktop login.
        # Do not replace the working renderer until GNOME actually exports it.
        check = run('/usr/bin/python3', str(library / 'bridge.py'), '--check')
        if check.returncode == 0:
            result = run('systemctl', '--user', 'restart', 't1-touchbar.service')
            if result.returncode:
                raise RuntimeError('Renderer restart failed')
            print('GNOME Touch Bar bridge enabled now.')
        else:
            print('Selected for next login. GNOME must load the new extension at logout/login; current Touch Bar remains running.')
        return
    # Restore only our own current selection; never overwrite a later choice.
    if previous.get('selected_sha'):
        if not selection.is_symlink() and selection.exists() and sha(selection) == previous['selected_sha']:
            before = previous.get('selection_before')
            selection.unlink()
            if before and 'symlink' in before:
                selection.symlink_to(before['symlink'])
            elif before:
                atomic(selection, base64.b64decode(before['data']), before['mode'])
        else:
            raise RuntimeError('Renderer selection changed; preserving it and installed files')
        previous.pop('selected_sha', None)
        if not previous.get('extension_before'):
            settings.set_strv('enabled-extensions', [u for u in settings.get_strv('enabled-extensions') if u != UUID])
            Gio.Settings.sync()
        previous.pop('selection_before', None)
        previous.pop('extension_before', None)
        if previous.pop('accessibility_before', None) is False and accessibility.get_boolean('toolkit-accessibility'):
            accessibility.set_boolean('toolkit-accessibility', False)
            Gio.Settings.sync()
        atomic(journal, (json.dumps(previous, indent=2) + '\n').encode(), 0o600)
        run('systemctl', '--user', 'restart', 't1-touchbar.service')
    if args.action == 'uninstall':
        for path, checksum in previous['files'].items():
            target = Path(path)
            if target.is_symlink() or target.exists() and sha(target) != checksum:
                raise RuntimeError(f'Preserving modified file: {path}')
        for path in previous['files']:
            Path(path).unlink(missing_ok=True)
        journal.unlink(missing_ok=True)
        print('Bridge removed; previous renderer restored.')
    else:
        print('Previous renderer restored.')


if __name__ == '__main__':
    main()
