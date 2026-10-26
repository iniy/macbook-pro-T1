# SPDX-License-Identifier: MIT
"""T1Bridge hardware IPC v1; no direct DRM, input, or fingerprint-device access."""
import array
import fcntl
import mmap
import os
import socket
import stat
import struct
import time

HEADER = struct.Struct('<4sHHII')
SOCKET = '/run/t1bridge/touchbar.sock'


class ProtocolError(RuntimeError):
    pass


def packet(kind, request, payload=b''):
    return HEADER.pack(b'T1HW', 1, kind, len(payload), request) + payload


def decode(data):
    if len(data) < HEADER.size or len(data) > 65536:
        raise ProtocolError('Invalid packet size')
    magic, version, kind, length, request = HEADER.unpack_from(data)
    if magic != b'T1HW' or version != 1 or length != len(data) - HEADER.size:
        raise ProtocolError('Invalid header')
    return kind, request, data[HEADER.size:]


def input_frame(data, width, height):
    if len(data) < 12:
        raise ProtocolError('Truncated input')
    stamp, fn, count, reserved = struct.unpack_from('<QBBH', data)
    if fn > 1 or count > 10 or reserved or len(data) != 12 + 12 * count:
        raise ProtocolError('Invalid input header')
    contacts, ids = [], set()
    for i in range(count):
        ident, tip, in_range, spare, x, y = struct.unpack_from('<BBBBII', data, 12 + i * 12)
        if ident > 15 or ident in ids or tip > 1 or in_range > 1 or spare or x >= width or y >= height:
            raise ProtocolError('Invalid contact')
        ids.add(ident)
        if tip and in_range:
            contacts.append((ident, x, y))
    return stamp, bool(fn), contacts


class Hardware:
    def __init__(self, path=SOCKET):
        self.sock = self.memory = None
        self.fd = None
        self.pending = {}
        self.sequence = 0
        self.frame_id = 0
        self.busy = False
        try:
            self._connect(path)
        except BaseException:
            self.close()
            raise

    def _connect(self, path):
        info = os.stat(path, follow_symlinks=False)
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != 0:
            raise ProtocolError('Hardware socket identity failed')
        for features in (0x3f, 0x2f, 0x37, 0x27):
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET | socket.SOCK_CLOEXEC)
            self.sock.settimeout(1)
            self.sock.connect(path)
            _, uid, _ = struct.unpack('3i', self.sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if uid != 0:
                raise ProtocolError('Hardware peer is not root')
            self.sock.sendall(packet(1, 1, struct.pack('<HHQ', 1, 0, features)))
            kind, request, data = self.receive()
            if kind == 0x8003 and data == struct.pack('<I', 2):
                self.sock.close()
                continue
            if kind != 0x8001 or request != 1 or len(data) != 20:
                raise ProtocolError('Hardware negotiation failed')
            minor, spare, width, height, fmt, buffers = struct.unpack('<HHIIII', data)
            if spare or minor > 1 or fmt != 1 or not 1 <= width <= 8192 or not 1 <= height <= 1024 or not 1 <= buffers <= 3:
                raise ProtocolError('Unsupported display format')
            self.minor, self.width, self.height, self.features = minor, width, height, features
            break
        else:
            raise ProtocolError('Required hardware features missing')
        self.sequence = 1
        self.fd = os.memfd_create('t1-gnome-frame', os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
        size = self.width * self.height * 4
        os.ftruncate(self.fd, size)
        self.memory = mmap.mmap(self.fd, size)
        fcntl.fcntl(self.fd, fcntl.F_ADD_SEALS,
                    fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SEAL)
        self.send(2, struct.pack('<IIQ', 1, self.width * 4, size), self.fd)
        # Drain any input frames until the registration acknowledgement arrives.
        deadline = time.monotonic() + 2
        while self.pending and time.monotonic() < deadline:
            self.event()
        if self.pending:
            raise ProtocolError('Buffer registration timed out')
        self.sock.settimeout(0.04)

    def receive(self):
        data, ancillary, flags, _ = self.sock.recvmsg(65536, socket.CMSG_SPACE(16), socket.MSG_CMSG_CLOEXEC)
        # Never leak unsolicited descriptors, even from a malformed response.
        for level, kind, value in ancillary:
            if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                descriptors = array.array('i')
                descriptors.frombytes(value[:len(value) // descriptors.itemsize * descriptors.itemsize])
                for fd in descriptors:
                    os.close(fd)
        if flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC) or ancillary or not data:
            raise ProtocolError('Hardware transport closed or malformed')
        return decode(data)

    def send(self, kind, payload=b'', fd=None):
        self.sequence += 1
        if self.sequence > 0xffffffff or len(self.pending) >= 16:
            raise ProtocolError('Request limit exceeded')
        ancillary = [] if fd is None else [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array('i', [fd]))]
        data = packet(kind, self.sequence, payload)
        if self.sock.sendmsg([data], ancillary) != len(data):
            raise ProtocolError('Short packet write')
        self.pending[self.sequence] = (kind, time.monotonic())

    def submit(self):
        if self.busy:
            return False
        self.frame_id += 1
        self.send(3, struct.pack('<IQI', 1, self.frame_id, 0))
        self.busy = True
        self.submitted_at = time.monotonic()
        return True

    def event(self, timeout=.04):
        if self.busy and time.monotonic() - getattr(self, 'submitted_at', time.monotonic()) > 3:
            raise ProtocolError('Frame release timed out')
        if any(time.monotonic() - started > 3 for _, started in self.pending.values()):
            raise ProtocolError('Hardware response timed out')
        self.sock.settimeout(timeout)
        try:
            kind, request, data = self.receive()
        except socket.timeout:
            return None
        if kind == 0x9002 and request == 0:
            return input_frame(data, self.width, self.height)
        if kind == 0x9001 and request == 0:
            if len(data) != 12 or struct.unpack('<IQ', data) != (1, self.frame_id) or not self.busy:
                raise ProtocolError('Invalid frame release')
            self.busy = False
        elif kind in (0x8002, 0x8003) and request in self.pending:
            operation, _ = self.pending.pop(request)
            if kind == 0x8002 and data:
                raise ProtocolError('Malformed acknowledgement')
            if kind == 0x8003:
                if len(data) != 4 or not 1 <= struct.unpack('<I', data)[0] <= 10:
                    raise ProtocolError('Malformed error')
                if operation in (2, 3):
                    raise ProtocolError('Frame rejected')
                # An unavailable brightness/cancellation action is not fatal.
        else:
            raise ProtocolError('Unexpected hardware response')
        return None

    def close(self):
        if self.memory is not None:
            self.memory.close()
            self.memory = None
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        if self.sock is not None:
            self.sock.close()
            self.sock = None
