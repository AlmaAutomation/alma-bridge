/*
 * Alma native runtime PE64 loader (Milestone 2).
 * mmap image, apply DIR64 relocations, patch kernel32 IAT, invoke entry.
 */
#define _GNU_SOURCE
#include "pe_loader.h"

#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#ifdef __x86_64__
#define MS_ABI __attribute__((ms_abi))
#else
#define MS_ABI
#endif

/* Forward declarations for kernel32 shims (defined in kernel32_shim.c). */
void *alma_shim_resolve_import(const char *name);

#define IMAGE_DOS_SIGNATURE 0x5A4D
#define IMAGE_NT_SIGNATURE 0x00004550
#define IMAGE_NT_OPTIONAL_HDR64_MAGIC 0x20B
#define IMAGE_FILE_MACHINE_AMD64 0x8664
#define IMAGE_DIRECTORY_ENTRY_IMPORT 1
#define IMAGE_DIRECTORY_ENTRY_BASERELOC 5
#define IMAGE_REL_BASED_ABSOLUTE 0
#define IMAGE_REL_BASED_DIR64 10

typedef struct {
    uint64_t image_base;
    uint32_t size_of_image;
    uint32_t size_of_headers;
    uint32_t address_of_entry_point;
    uint32_t import_rva;
    uint32_t import_size;
    uint32_t reloc_rva;
    uint32_t reloc_size;
    uint16_t num_sections;
    uint16_t machine;
} pe_info_t;

static int read_u16(const uint8_t *data, size_t len, size_t off, uint16_t *out) {
    if (off + 2 > len) return -1;
    *out = *(const uint16_t *)(data + off);
    return 0;
}

static int read_u32(const uint8_t *data, size_t len, size_t off, uint32_t *out) {
    if (off + 4 > len) return -1;
    *out = *(const uint32_t *)(data + off);
    return 0;
}

static int read_u64(const uint8_t *data, size_t len, size_t off, uint64_t *out) {
    if (off + 8 > len) return -1;
    *out = *(const uint64_t *)(data + off);
    return 0;
}

static int parse_pe64(const uint8_t *data, size_t len, pe_info_t *info) {
    uint32_t e_lfanew = 0;
    if (read_u32(data, len, 60, &e_lfanew) != 0) return -1;
    if (e_lfanew + 4 > len) return -1;
    uint32_t sig = 0;
    if (read_u32(data, len, e_lfanew, &sig) != 0 || sig != IMAGE_NT_SIGNATURE) return -1;
    size_t coff = e_lfanew + 4;
    if (read_u16(data, len, coff, &info->machine) != 0) return -1;
    if (info->machine != IMAGE_FILE_MACHINE_AMD64) return -1;
    if (read_u16(data, len, coff + 2, &info->num_sections) != 0) return -1;
    uint16_t opt_size = 0;
    if (read_u16(data, len, coff + 16, &opt_size) != 0) return -1;
    size_t opt = coff + 20;
    uint16_t magic = 0;
    if (read_u16(data, len, opt, &magic) != 0 || magic != IMAGE_NT_OPTIONAL_HDR64_MAGIC) return -1;
    if (read_u32(data, len, opt + 16, &info->address_of_entry_point) != 0) return -1;
    if (read_u64(data, len, opt + 24, &info->image_base) != 0) return -1;
    if (read_u32(data, len, opt + 56, &info->size_of_image) != 0) return -1;
    if (read_u32(data, len, opt + 60, &info->size_of_headers) != 0) return -1;
    size_t dd = opt + 112;
    if (read_u32(data, len, dd + IMAGE_DIRECTORY_ENTRY_IMPORT * 8, &info->import_rva) != 0) return -1;
    if (read_u32(data, len, dd + IMAGE_DIRECTORY_ENTRY_IMPORT * 8 + 4, &info->import_size) != 0) return -1;
    if (read_u32(data, len, dd + IMAGE_DIRECTORY_ENTRY_BASERELOC * 8, &info->reloc_rva) != 0) return -1;
    if (read_u32(data, len, dd + IMAGE_DIRECTORY_ENTRY_BASERELOC * 8 + 4, &info->reloc_size) != 0) return -1;
    return 0;
}

typedef struct {
    uint32_t virtual_address;
    uint32_t virtual_size;
    uint32_t size_of_raw_data;
    uint32_t pointer_to_raw_data;
} sec_info_t;

static int load_sections(const uint8_t *data, size_t len, size_t coff, uint16_t nsec, sec_info_t *secs) {
    size_t sec_off = coff + 20 + 240; /* COFF + PE32+ optional header (fixed 240 for standard) */
    /* Recompute optional header size from COFF */
    uint16_t opt_size = 0;
    read_u16(data, len, coff + 16, &opt_size);
    sec_off = coff + 20 + opt_size;
    for (uint16_t i = 0; i < nsec; i++) {
        size_t off = sec_off + (size_t)i * 40;
        if (off + 40 > len) return -1;
        if (read_u32(data, len, off + 8, &secs[i].virtual_size) != 0) return -1;
        if (read_u32(data, len, off + 12, &secs[i].virtual_address) != 0) return -1;
        if (read_u32(data, len, off + 16, &secs[i].size_of_raw_data) != 0) return -1;
        if (read_u32(data, len, off + 20, &secs[i].pointer_to_raw_data) != 0) return -1;
    }
    return 0;
}

static uint32_t rva_to_offset(const sec_info_t *secs, uint16_t nsec, uint32_t rva) {
    for (uint16_t i = 0; i < nsec; i++) {
        uint32_t vs = secs[i].virtual_size;
        if (vs == 0) vs = secs[i].size_of_raw_data;
        if (rva >= secs[i].virtual_address && rva < secs[i].virtual_address + vs) {
            return secs[i].pointer_to_raw_data + (rva - secs[i].virtual_address);
        }
    }
    return 0;
}

static void apply_relocs(uint8_t *image, const uint8_t *file, size_t file_len,
                         const sec_info_t *secs, uint16_t nsec,
                         uint32_t reloc_rva, uint32_t reloc_size, int64_t delta) {
    if (delta == 0 || reloc_rva == 0 || reloc_size == 0) return;
    uint32_t offset = rva_to_offset(secs, nsec, reloc_rva);
    uint32_t end = offset + reloc_size;
    uint32_t pos = offset;
    while (pos + 8 <= end && pos + 8 <= file_len) {
        uint32_t page_rva = *(const uint32_t *)(file + pos);
        uint32_t block_size = *(const uint32_t *)(file + pos + 4);
        if (block_size < 8) break;
        pos += 8;
        uint32_t block_end = pos + block_size - 8;
        while (pos + 2 <= block_end && pos + 2 <= file_len) {
            uint16_t entry = *(const uint16_t *)(file + pos);
            pos += 2;
            uint16_t type = entry >> 12;
            uint16_t rel_off = entry & 0xFFF;
            if (type == IMAGE_REL_BASED_ABSOLUTE) continue;
            uint32_t target_rva = page_rva + rel_off;
            if (type == IMAGE_REL_BASED_DIR64) {
                uint64_t *slot = (uint64_t *)(image + target_rva);
                *slot = (uint64_t)((int64_t)(*slot) + delta);
            }
        }
    }
}

static const char *read_cstr(const uint8_t *data, size_t len, uint32_t off) {
    if (off >= len) return "";
    return (const char *)(data + off);
}

static int str_ieq(const char *a, const char *b) {
    while (*a && *b) {
        char ca = (*a >= 'A' && *a <= 'Z') ? (*a + 32) : *a;
        char cb = (*b >= 'A' && *b <= 'Z') ? (*b + 32) : *b;
        if (ca != cb) return 0;
        a++;
        b++;
    }
    return *a == *b;
}

static int patch_imports(uint8_t *image, const uint8_t *file, size_t file_len,
                         const sec_info_t *secs, uint16_t nsec,
                         uint32_t import_rva) {
    if (import_rva == 0) return -1;
    uint32_t desc_off = rva_to_offset(secs, nsec, import_rva);
    uint32_t pos = desc_off;
    while (pos + 20 <= file_len) {
        uint32_t oft = *(const uint32_t *)(file + pos);
        uint32_t name_rva = *(const uint32_t *)(file + pos + 12);
        uint32_t first_thunk = *(const uint32_t *)(file + pos + 16);
        if (oft == 0 && name_rva == 0 && first_thunk == 0) break;
        uint32_t name_off = rva_to_offset(secs, nsec, name_rva);
        const char *dll = read_cstr(file, file_len, name_off);
        if (!str_ieq(dll, "kernel32.dll")) return -1;
        uint32_t iat_rva = first_thunk ? first_thunk : oft;
        uint32_t thunk_off = rva_to_offset(secs, nsec, oft ? oft : first_thunk);
        uint32_t iat_pos = iat_rva;
        uint32_t tpos = thunk_off;
        while (tpos + 8 <= file_len) {
            uint64_t val = *(const uint64_t *)(file + tpos);
            if (val == 0) break;
            const char *fname = NULL;
            char ord_buf[32];
            if (val & (1ULL << 63)) {
                snprintf(ord_buf, sizeof(ord_buf), "ordinal_%u", (unsigned)(val & 0xFFFF));
                fname = ord_buf;
            } else {
                uint32_t hint_off = rva_to_offset(secs, nsec, (uint32_t)val);
                fname = read_cstr(file, file_len, hint_off + 2);
            }
            void *shim = alma_shim_resolve_import(fname);
            if (!shim) return -1;
            *(uint64_t *)(image + iat_pos) = (uint64_t)(uintptr_t)shim;
            tpos += 8;
            iat_pos += 8;
        }
        pos += 20;
    }
    return 0;
}

typedef void (*entry_fn_t)(void) MS_ABI;

int32_t alma_pe_load_and_run(
    const uint8_t *pe_data,
    size_t pe_size,
    uint64_t load_base_override,
    uint32_t entry_rva_out,
    int *entrypoint_invoked_out
) {
    (void)entry_rva_out;
    pe_info_t info;
    if (parse_pe64(pe_data, pe_size, &info) != 0) return -1;

    sec_info_t *secs = calloc(info.num_sections, sizeof(sec_info_t));
    if (!secs) return -1;
    size_t coff = *(const uint32_t *)(pe_data + 60) + 4;
    if (load_sections(pe_data, pe_size, coff, info.num_sections, secs) != 0) {
        free(secs);
        return -1;
    }

    uint64_t load_base = load_base_override ? load_base_override : info.image_base;
    (void)load_base;

    size_t map_size = info.size_of_image;
    void *map = mmap(NULL, map_size, PROT_READ | PROT_WRITE | PROT_EXEC,
                     MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (map == MAP_FAILED) {
        free(secs);
        return -1;
    }
    memset(map, 0, map_size);

    size_t hdr_copy = info.size_of_headers;
    if (hdr_copy > pe_size) hdr_copy = pe_size;
    memcpy(map, pe_data, hdr_copy);

    for (uint16_t i = 0; i < info.num_sections; i++) {
        if (secs[i].size_of_raw_data == 0) continue;
        uint32_t src = secs[i].pointer_to_raw_data;
        uint32_t dst = secs[i].virtual_address;
        if (src + secs[i].size_of_raw_data > pe_size) continue;
        memcpy((uint8_t *)map + dst, pe_data + src, secs[i].size_of_raw_data);
    }

    int64_t delta = (int64_t)((uintptr_t)map - info.image_base);

    apply_relocs((uint8_t *)map, pe_data, pe_size, secs, info.num_sections,
                 info.reloc_rva, info.reloc_size, delta);

    if (patch_imports((uint8_t *)map, pe_data, pe_size, secs, info.num_sections, info.import_rva) != 0) {
        munmap(map, map_size);
        free(secs);
        return -1;
    }

    entry_fn_t entry = (entry_fn_t)((uint8_t *)map + info.address_of_entry_point);

    if (entrypoint_invoked_out) *entrypoint_invoked_out = 1;
    entry();

    munmap(map, map_size);
    free(secs);
    return 0;
}
