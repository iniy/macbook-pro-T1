#!/usr/bin/env python3
"""Compile the actual slot/open/raw-event functions with a minimal HID test fixture."""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'driver/apple-ibridge.c').read_text()


def function(name):
    start = source.index('static int ' + name + '(')
    brace = source.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


fixture = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <errno.h>
typedef unsigned char u8;
struct hid_device { void *driver_data; unsigned vendor, product; };
struct hid_report { int type; };
struct { unsigned vendor, product; } appleib_sub_hid_ids[] = {{0x1d6b,0x0301},{0x1d6b,0x0302}};
struct appleib_hid_dev_info { struct hid_device *hdev; struct hid_device *sub_hdevs[2]; bool sub_open[2]; };
#define ARRAY_SIZE(x) (sizeof(x)/sizeof((x)[0]))
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,y) ((x)=(y))
#define hid_get_drvdata(x) ((x)->driver_data)
static struct hid_device *last;
static void hid_input_report(struct hid_device *d, int type, u8 *data, int size, int flag) {
    (void)type; (void)data; (void)size; (void)flag;
    assert(d != NULL); last = d;
}
'''
main = r'''
int main(void) {
    struct appleib_hid_dev_info info = {0};
    struct hid_device parent = { .driver_data=&info };
    struct hid_device als = {&info,0x1d6b,0x0302}, tb = {&info,0x1d6b,0x0301};
    struct hid_device unknown = {&info,0x1d6b,0xffff};
    struct hid_report report = {0}; u8 data = 0;
    /* Combined HID descriptor has ALS first, nested collections, then display. */
    assert(appleib_set_open(&als, true) == 0);
    assert(!info.sub_open[0] && info.sub_open[1]);
    /* Open callback can precede publication: forwarding must not dereference NULL. */
    appleib_hid_raw_event(&parent, &report, &data, 1);
    assert(last == NULL);
    info.sub_hdevs[1] = &als;
    appleib_hid_raw_event(&parent, &report, &data, 1);
    assert(last == &als);
    assert(appleib_set_open(&tb, true) == 0);
    info.sub_hdevs[0] = &tb;
    assert(info.sub_open[0] && info.sub_open[1]);
    assert(appleib_set_open(&als, false) == 0);
    appleib_hid_raw_event(&parent, &report, &data, 1);
    assert(last == &tb);
    assert(appleib_set_open(&unknown, true) == -ENODEV);
    return 0;
}
'''
with tempfile.TemporaryDirectory() as tmp:
    c = Path(tmp) / 'slots.c'
    exe = Path(tmp) / 'slots'
    c.write_text(fixture + function('appleib_hid_raw_event') + '\n' + function('appleib_set_open') + main)
    subprocess.run([os.environ.get('CC', 'cc'), '-Wall', '-Wextra', '-Werror',
                    '-Wno-sign-compare', '-fsanitize=address,undefined', str(c), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
print('PASS actual HID slot functions: ALS-first, pre-publication, close, unknown ID; ASan/UBSan')
