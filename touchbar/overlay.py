# SPDX-License-Identifier: MIT
"""Read only the public cosmetic Touch ID state; never open biometric material."""
import json
import os
import stat

PATH = '/run/t1bridge/touch-id-state.json'


def read_overlay(path=PATH):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_size > 1024:
                return None
            data = os.read(fd, 1025)
        finally:
            os.close(fd)
        if not data.endswith(b'\n') or len(data) > 1024:
            return None
        def unique(pairs):
            result = {}
            for k, v in pairs:
                if k in result:
                    raise ValueError('Duplicate field')
                result[k] = v
            return result
        value = json.loads(data, object_pairs_hook=unique)
        if type(value.get('version')) is not int or value['version'] not in (1, 2):
            return None
        fields = {'version', 'pid', 'state'} | ({'progress'} if value['version'] == 2 else set())
        if set(value) != fields or type(value['pid']) is not int or value['pid'] <= 0:
            return None
        if value['state'] not in ('enrollment', 'authenticate', 'approve', 'retry', 'success'):
            return None
        if value['version'] == 2 and (value['state'] != 'enrollment' or
                type(value['progress']) is not int or not 0 <= value['progress'] <= 100):
            return None
        os.kill(value['pid'], 0)
        return value
    except PermissionError:
        # kill(pid, 0) can legitimately deny access to a live root producer.
        if 'value' in locals():
            return value
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return None
