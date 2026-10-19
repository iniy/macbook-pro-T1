/* Local CLI adapter for UTM 4.6.5's QEMU framework; never passes host devices. */
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char **argv)
{
    const char *library = getenv("QEMU_FRAMEWORK");
    void *handle = library ? dlopen(library, RTLD_NOW | RTLD_GLOBAL) : NULL;
    if (!handle) {
        fprintf(stderr, "QEMU_FRAMEWORK: %s\n", dlerror());
        return 1;
    }
    if (strstr(library, "qemu-img")) {
        int (*img)(int, char **) = dlsym(handle, "main");
        if (!img) { fprintf(stderr, "%s\n", dlerror()); return 1; }
        return img(argc, argv);
    }
    void (*init)(int, char **, char **) = dlsym(handle, "qemu_init");
    int (*loop)(void) = dlsym(handle, "qemu_main_loop");
    void (*cleanup)(void) = dlsym(handle, "qemu_cleanup");
    if (!init || !loop || !cleanup) {
        fprintf(stderr, "Missing QEMU entry points\n"); return 1;
    }
    init(argc, argv, NULL);
    int result = loop();
    cleanup();
    return result;
}
