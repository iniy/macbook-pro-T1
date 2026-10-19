#!/usr/bin/env python3
"""Verify a Linux appended PKCS#7 signature against exactly one approved certificate.

Trust/enrollment is checked by the caller. OpenSSL verifies the content/signature
using only this certificate, without using embedded signer certificates.
"""
import gzip
import lzma
from pathlib import Path
import subprocess
import sys
import tempfile


def module_bytes(path):
    data = path.read_bytes()
    if data.startswith(b'\x28\xb5\x2f\xfd'):
        return subprocess.check_output(['zstd', '-dc', str(path)])
    if data.startswith(b'\x1f\x8b'):
        return gzip.decompress(data)
    if data.startswith(b'\xfd7zXZ\x00'):
        return lzma.decompress(data)
    return data


def verify(module, certificate):
    data = module_bytes(module)
    marker = b'~Module signature appended~\n'
    if not data.startswith(b'\x7fELF') or not data.endswith(marker):
        raise ValueError('Not a signed ELF kernel module')
    footer = data[-len(marker)-12:-len(marker)]
    if len(footer) != 12 or footer[2] != 2 or footer[3:8] != bytes(5):
        raise ValueError('Unsupported module signature format')
    length = int.from_bytes(footer[8:12], 'big')
    end = len(data) - len(marker) - 12
    if not 0 < length < end:
        raise ValueError('Invalid module signature length')
    with tempfile.TemporaryDirectory() as name:
        tmp = Path(name)
        (tmp / 'content').write_bytes(data[:end-length])
        (tmp / 'signature').write_bytes(data[end-length:end])
        subprocess.run(['openssl', 'x509', '-inform', 'DER', '-in', str(certificate),
                        '-out', str(tmp / 'certificate.pem')], check=True, capture_output=True)
        subprocess.run(['openssl', 'cms', '-verify', '-binary', '-inform', 'DER',
                        '-in', str(tmp / 'signature'), '-content', str(tmp / 'content'),
                        '-certfile', str(tmp / 'certificate.pem'), '-nointern', '-noverify',
                        '-out', '/dev/null'], check=True, capture_output=True)


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('Usage: check-signature.py MODULE CERTIFICATE.der')
    try:
        verify(Path(sys.argv[1]), Path(sys.argv[2]))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print('Module signature verification failed:', type(error).__name__, file=sys.stderr)
        raise SystemExit(1)
    print('PASS module signature verified against the specified certificate')
