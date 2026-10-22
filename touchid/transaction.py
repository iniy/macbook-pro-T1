# SPDX-License-Identifier: MIT
"""Journaled, conflict-aware file installation and rollback. Never touches EFI."""
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile


def safe(path):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise RuntimeError('Expected absolute normalized path')
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise RuntimeError('Symlink in managed path: ' + str(path))
    return path


def atomic(path, data, mode=0o600):
    safe(path)
    missing = []
    current = path.parent
    while not current.exists():
        missing.append(current)
        current = current.parent
    for directory in reversed(missing):
        directory.mkdir(mode=0o755)
        directory.chmod(0o755)
    name = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
            name = Path(f.name)
            os.fchmod(f.fileno(), mode)
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        name.replace(path)
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        if name:
            name.unlink(missing_ok=True)


class Transaction:
    def __init__(self, state, root=Path('/')):
        self.state = safe(state)
        self.root = safe(root)
        self.state.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.state.stat().st_mode & 0o077:
            raise RuntimeError('Transaction state must be private (0700)')
        self.journal = self.state / 'journal.json'
        self.entries = json.loads(self.journal.read_text()) if self.journal.exists() else []

    def save(self):
        atomic(self.journal, (json.dumps(self.entries, indent=2) + '\n').encode())

    def target(self, name):
        if Path(name).is_absolute() or '..' in Path(name).parts:
            raise RuntimeError('Unsafe transaction name')
        return safe(self.root / name)

    def put(self, name, data, mode=0o644, replace=False):
        target = self.target(name)
        checksum = hashlib.sha256(data).hexdigest()
        prior = next((r for r in self.entries if r['name'] == name), None)
        if prior:
            if prior['sha256'] == checksum and target.is_file() and target.read_bytes() == data:
                return
            raise RuntimeError('Existing transaction differs; rollback before upgrading')
        if target.exists() and (not target.is_file() or not replace):
            raise RuntimeError('Refusing to replace existing file: ' + name)
        entry = {'name': name, 'sha256': checksum, 'mode': mode, 'before': None}
        if target.exists():
            before = 'before/' + str(len(self.entries))
            atomic(self.state / before, target.read_bytes())
            entry.update(before=before, before_mode=stat.S_IMODE(target.stat().st_mode))
        self.entries.append(entry)
        self.save()  # Write-ahead; interrupted copies are recoverable.
        atomic(target, data, mode)

    def rollback(self, names=None):
        """Restore all owned files, or only a failed extension of this transaction."""
        conflicts = []
        for entry in list(reversed(self.entries)):
            if names is not None and entry['name'] not in names:
                continue
            target = self.target(entry['name'])
            before = (self.state / entry['before']).read_bytes() if entry['before'] else None
            if target.exists() and not target.is_file():
                conflicts.append(entry['name'])
                continue
            current = target.read_bytes() if target.is_file() else None
            if current == before:
                pass  # Includes a journaled but not yet written file.
            elif current is not None and hashlib.sha256(current).hexdigest() != entry['sha256']:
                conflicts.append(entry['name'])
                continue
            elif before is None:
                target.unlink(missing_ok=True)
            else:
                atomic(target, before, entry['before_mode'])
            self.entries.remove(entry)
            self.save()
        if conflicts:
            raise RuntimeError('Local edits preserved; manual recovery required: ' + ', '.join(conflicts))
