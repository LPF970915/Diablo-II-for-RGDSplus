/* Reuse the verified retail decompressor with the preserved classic adapter. */
#define _GNU_SOURCE
#define D2_RETAIL_MPQ_STANDALONE
#include <link.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
static uintptr_t image;
static const int installed = 1;
static int find_image(struct dl_phdr_info *info, size_t bytes, void *unused) {
    (void)bytes; (void)unused;
    if (info->dlpi_name && strstr(info->dlpi_name, "/libd2game_sa_arm.exe.so")) {
        image = info->dlpi_addr;
        return 1;
    }
    return 0;
}
static void *install_entry(uintptr_t offset, uint32_t first, uint32_t second, void *function) {
    dl_iterate_phdr(find_image, NULL);
    if (!image) return NULL;
    uint32_t *entry = (void *)(image + offset);
    if (entry[0] != first || entry[1] != second) return NULL;
    uint32_t *relay = mmap(NULL, 4096, PROT_READ | PROT_WRITE,
                          MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (relay == MAP_FAILED) return NULL;
    relay[0] = first; relay[1] = second;
    relay[2] = 0xe51ff004; relay[3] = (uintptr_t)(entry + 2);
    __builtin___clear_cache((char *)relay, (char *)relay + 16);
    if (mprotect(relay, 4096, PROT_READ | PROT_EXEC) != 0) return NULL;
    uintptr_t page = (uintptr_t)entry & ~4095u;
    if (mprotect((void *)page, 4096, PROT_READ | PROT_WRITE | PROT_EXEC) != 0) return NULL;
    entry[0] = 0xe51ff004; entry[1] = (uintptr_t)function;
    __builtin___clear_cache((char *)entry, (char *)entry + 8);
    mprotect((void *)page, 4096, PROT_READ | PROT_EXEC);
    return relay;
}
#include "../../release/adapter/retail_probe.c"
