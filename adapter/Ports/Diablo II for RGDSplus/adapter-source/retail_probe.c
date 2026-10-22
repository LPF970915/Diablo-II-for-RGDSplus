/* Release wrapper: keep the validated dual-screen adapter unchanged. */
#ifndef D2_RETAIL_MPQ_STANDALONE
#include "world_probe.c"
#endif
#include <dlfcn.h>

extern void *legacy_dlopen(const char *, int);
extern void *legacy_dlsym(void *, const char *);
__asm__(".symver legacy_dlopen,dlopen@GLIBC_2.4");
__asm__(".symver legacy_dlsym,dlsym@GLIBC_2.4");

typedef int (*mpq_unpack_fn)(void *, unsigned *, const unsigned char *, unsigned);
typedef int (*zlib_unpack_fn)(unsigned char *, unsigned long *, const unsigned char *, unsigned long);
static mpq_unpack_fn mpq_unpack_original;
static zlib_unpack_fn retail_uncompress;
static unsigned retail_zlib_blocks, retail_zlib_failures;

/* The statically translated Storm_552 supports masks 0xC9, excluding zlib
 * (0x02). Blizzard's digital MPQs use 0x02 for their optional metadata.
 * Handle that exact mask with the bundled ARM32 zlib; retain original
 * behavior for uncompressed blocks and every other compression mask. */
static int retail_mpq_unpack(void *output, unsigned *output_size,
                             const unsigned char *input, unsigned input_size) {
    if (output && output_size && input && input_size > 1 &&
        *output_size > input_size && input[0] == 0x02) {
        unsigned long available = *output_size;
        int result = retail_uncompress(output, &available, input + 1, input_size - 1);
        if (result == 0 && available <= *output_size) {
            *output_size = available;
            ++retail_zlib_blocks;
            return 1;
        }
        ++retail_zlib_failures;
        fprintf(stderr, "RETAIL_MPQ: invalid zlib sector (%d)\n", result);
        return 0;
    }
    return mpq_unpack_original(output, output_size, input, input_size);
}

__attribute__((constructor)) static void start_retail_mpq(void) {
    if (!installed) return;
    void *library = legacy_dlopen("/tmp/diablo2-wine/port-libs/libz.so.1", RTLD_NOW | RTLD_LOCAL);
    if (!library || !(retail_uncompress = (zlib_unpack_fn)legacy_dlsym(library, "uncompress"))) {
        fprintf(stderr, "RETAIL_MPQ: bundled ARM32 zlib unavailable\n");
        return;
    }
    mpq_unpack_original = install_entry(0x141928, 0xe92d4ff0, 0xe2925000, retail_mpq_unpack);
    fprintf(stderr, "RETAIL_MPQ: zlib support %s\n", mpq_unpack_original ? "enabled" : "identity mismatch");
}

__attribute__((destructor)) static void stop_retail_mpq(void) {
    fprintf(stderr, "RETAIL_MPQ: zlib blocks=%u failures=%u\n", retail_zlib_blocks, retail_zlib_failures);
}
