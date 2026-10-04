# Shell tools usage

This page documents **direct shell-tool usage** for this branch.

> Branch support scope: `VERSION=2025|SP1|SP2`

## build.sh

Build FIP (and BL2 when enabled by config) directly.

### build.sh basic usage

```bash
chmod +x build.sh
BOARD=sn_r1 ./build.sh
```

### build.sh common examples

```bash
# nonmbm build
BOARD=zbt_z8103ax-c VARIANT=NONMBM ./build.sh

# multi-layout on SP2
BOARD=cmcc_a10 VERSION=SP2 MULTI_LAYOUT=1 ./build.sh

# with SIMG and SP1
BOARD=ruijie_rg-x60-new VERSION=SP1 MULTI_LAYOUT=1 SIMG=1 ./build.sh

# clean build outputs
./build.sh --clean
```

### build.sh key variables

- `BOARD` (required)
- `VERSION=2025|SP1|SP2`
- `VARIANT=default|ubootmod|nonmbm|openwrt`
- `MULTI_LAYOUT=0|1`
- `FIXED_MTDPARTS=0|1`
- `FSTHEME=bootstrap|gl|mtk`
- `SIMG=0|1`
- `UBIMNG=0|1` (enable UBI volume management in failsafe Web UI)
- `TELNETD=0|1` (enable RFC 854 compliant telnet server)
- `SILENT=Y|N`
- `COPY_BL2=0|1`
- `--clean` to clean build outputs

---

## compile_atf.sh

Build BL2 from configs under `mt798x_atf`.

### compile_atf.sh basic usage

```bash
chmod +x compile_atf.sh
./compile_atf.sh
```

### compile_atf.sh common examples

```bash
# choose version
VERSION=SP1 ./compile_atf.sh

# select sub-directory configs
CFG_SUBDIR=normal VERSION=2025 ./compile_atf.sh

# custom output directory
OUTPUT_DIR=output_bl2 VERSION=SP2 ./compile_atf.sh

# variant helpers for normal/* configs
VARIANT=NONMBM VERSION=2025 ./compile_atf.sh
VARIANT=UBOOTMOD VERSION=2025 ./compile_atf.sh

# overclock examples
OC7981=16 VERSION=2025 ./compile_atf.sh
OC7986=23 VERSION=2025 ./compile_atf.sh
```

### compile_atf.sh key variables

- `VERSION=2025|SP1|SP2`
- `ATF_DIR` (optional override)
- `ATFCFG_DIR` (default `mt798x_atf`)
- `CFG_SUBDIR` (optional)
- `OUTPUT_DIR` (default `output_bl2`)
- `VARIANT=NONMBM|UBOOTMOD` (only for `normal/*` configs)
- `OC7981=13..18`
- `OC7986=16..25`

---

## generate_gpt.sh

Generate GPT binaries from JSON layouts.

### generate_gpt.sh basic usage

```bash
chmod +x generate_gpt.sh
./generate_gpt.sh
```

### generate_gpt.sh common examples

```bash
# choose version-specific gpt tools
VERSION=SP1 ./generate_gpt.sh

# build sdmmc gpt
SDMMC=1 ./generate_gpt.sh

# show info from mt798x_gpt_bin/*.bin|*.img
SHOW=1 ./generate_gpt.sh

# draw partition png
DRAW=1 ./generate_gpt.sh
```

### generate_gpt.sh key variables

- `VERSION=2025|SP1|SP2`
- `SHOW=0|1`
- `DRAW=0|1|notitle`
- `SDMMC=0|1`

---

## Recommended path

For daily usage, prefer `make` commands from repository root:

- `make`
- `make BOARD=<board> [VERSION=...] [VARIANT=...] ...`
- `make atf [VERSION=...] ...`
- `make gpt [VERSION=...] ...`
- `make help`
