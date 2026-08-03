#ifndef ALMA_PE_LOADER_H
#define ALMA_PE_LOADER_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Load PE64 from bytes, apply relocations, patch IAT, invoke entry. Returns exit code or -1 on error. */
int32_t alma_pe_load_and_run(
    const uint8_t *pe_data,
    size_t pe_size,
    uint64_t load_base_override,
    uint32_t entry_rva_out,
    int *entrypoint_invoked_out
);

#ifdef __cplusplus
}
#endif

#endif /* ALMA_PE_LOADER_H */
