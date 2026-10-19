#!/usr/bin/env python3
"""Exercise the actual probe/suspend/resume guard with ACPI calls counted, not run."""
from pathlib import Path
import os
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'driver/apple-ibridge.c').read_text()
assert 'static int skip_acpi_power = 1;' in source


def extract(name):
    match = re.search(r'static (?:bool|int|struct appleib_device \*)\s*' + name + r'\(', source)
    start = match.start()
    brace = source.index('{', start)
    depth, end = 1, brace + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


fixture = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <errno.h>
typedef void *acpi_handle;
typedef int acpi_status;
typedef int pm_message_t;
struct device { int unused; };
struct platform_device { struct device dev; void *data; };
struct appleib_device { acpi_handle asoc_socw; };
static int skip_acpi_power = 1, lookups, executions, registrations;
static int appleib_hid_driver;
#define DMI_PRODUCT_NAME 1
#define GFP_KERNEL 0
#define ACPI_HANDLE(x) ((void *)(x))
#define ACPI_FAILURE(x) ((x) != 0)
#define dev_err(...) ((void)0)
#define dev_warn(...) ((void)0)
#define ERR_PTR(x) ((void *)(intptr_t)(x))
#define PTR_ERR(x) ((int)(intptr_t)(x))
#define IS_ERR(x) ((intptr_t)(x) < 0)
#define platform_get_drvdata(x) ((x)->data)
#define platform_set_drvdata(x,y) ((x)->data=(y))
#define dmi_get_system_info(x) "MacBookPro13,2"
#define str_has_prefix(x,p) (!strncmp((x),(p),strlen(p)))
static void *devm_kzalloc(struct device *d, size_t n, int flags) {
    (void)d; (void)flags; return calloc(1,n);
}
static int acpi_get_handle(void *d, const char *name, void **out) {
    (void)d; (void)name; *out=(void *)1; ++lookups; return 0;
}
static int acpi_execute_simple_method(void *handle, void *path, int value) {
    (void)handle; (void)path; (void)value; ++executions; return 0;
}
static int hid_register_driver(int *driver) { (void)driver; ++registrations; return 0; }
'''
main = r'''
int main(void) {
    struct platform_device p = {0};
    int invalid[] = {0,-1,2};
    for (unsigned i=0; i<sizeof(invalid)/sizeof(invalid[0]); ++i) {
        skip_acpi_power=invalid[i];
        assert(appleib_probe(&p) == -EINVAL);
        assert(!lookups && !executions && !registrations);
    }
    skip_acpi_power=1;
    assert(appleib_probe(&p) == 0);
    assert(lookups == 1 && registrations == 1 && executions == 0);
    assert(appleib_suspend(&p,0) == 0);
    assert(appleib_resume(&p) == 0);
    assert(executions == 0);
    free(p.data);
    return 0;
}
'''
functions = ['appleib_skip_acpi_power', 'appleib_alloc_device', 'appleib_probe',
             'appleib_suspend', 'appleib_resume']
with tempfile.TemporaryDirectory() as name:
    c = Path(name) / 'guard.c'
    exe = Path(name) / 'guard'
    c.write_text(fixture + '\n'.join(extract(n) for n in functions) + main)
    subprocess.run([os.environ.get('CC', 'cc'), '-Wall', '-Wextra', '-Werror',
                    '-Wno-unused-parameter', '-fsanitize=address,undefined',
                    str(c), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
print('PASS actual probe/suspend/resume: overrides rejected; skip=1 executes zero ACPI methods; ASan/UBSan')
