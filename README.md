# Netis NX62 / Netcore N60 Pro: multi-layout bootloader

**English** | [Русский](README.ru.md)

BL2 + FIP (BL31 + U-Boot with a DHCP server and a failsafe web UI) for the
**Netis NX62** (hardware twin of the **Netcore N60 Pro**): MT7986A, DDR4
512 MB / 1 GB / 2 GB, 128 MB SPI-NAND (2 KB page, 128 KB block).

One bootloader boots both the **stock firmware** and **official OpenWrt**.
The flash layout is selected in the web UI when flashing firmware:

| Layout (`mtd_layout`) | Firmware | `ubi` partition |
| --- | --- | --- |
| `default` | stock Netis/Netcore firmware; builds on the stock NMBM layout (Kwrt, ImmortalWrt mt798x, etc.) | `117248k` (0x580000–0x7800000) |
| `openwrt` | official OpenWrt 24.10 / 25.12 and ImmortalWrt 24.10+, device `netcore_n60-pro` | `125440k` (0x580000–0x8000000) |

The start of the flash is the same for both layouts:
`1024k(bl2),512k(u-boot-env),2048k(factory),2048k(fip)`.

The bootloader is based on
[Yuzhii0718/bl-mt798x-dhcpd](https://github.com/Yuzhii0718/bl-mt798x-dhcpd).
This repository contains only the NX62 board files and patches; the upstream
sources are downloaded at build time.

## Differences from upstream bl-mt798x-dhcpd

**New board `netis_nx62`**

- **No NMBM.** BL2 skips bad blocks (`_NAND_SKIP_BAD`) and U-Boot works on
  the raw `spi-nand0`, like the official OpenWrt bootloader. Upstream
  `netcore_n60-pro` (default variant) uses NMBM: on every boot it looks for the
  NMBM tables in the last 8 MB of the flash and writes new ones if they are
  missing, i.e. over the UBI blocks of official OpenWrt, which uses the flash
  up to the end.
- **Two layouts** (`default` and `openwrt`, see above) instead of a single
  fixed one. The `default` layout never touches the NMBM area, so the stock
  kernel keeps its NMBM tables.
- The web UI shows the model as **Netis NX62**; LEDs match the OpenWrt DTS
  (Wi-Fi LED on GPIO 1).
- `MTK_FDT_BOOTARGS_FALLBACK`: if a layout has no command line, the kernel
  gets the bootargs from its own FDT.

**Fixes (patches)**

- `0001` — **TRNG for the stock kernel.** ATF 2025/2026 restricts the
  hardware random number generator to the secure world (SMC only). The stock
  kernel 5.4 reads the TRNG registers directly and gets hwrng errors. The new
  ATF option `_MT7986_TRNG_NS_ACCESS` (enabled for NX62) keeps both direct
  access (stock) and the SMC interface (OpenWrt) working.
- `0002` — **Clean layout switch.** If UBI is still attached to the old
  layout (for example after a failed boot attempt), upstream U-Boot cannot
  recreate the partitions and writes the firmware into the old `ubi`
  partition. With the patch, UBI is detached on a layout switch, and the `ubi`
  partition of the new layout is erased before writing.

**Build checks**

The build fails instead of producing an image if BL2 or U-Boot is built with
NMBM, a layout is missing, the model is wrong, an image doesn't fit its
partition, or a layout writes firmware to a partition other than `ubi`.

## Repository layout

| File | Purpose |
| --- | --- |
| `build.sh` | fetches upstream, adds the NX62 files, applies the patches, builds and verifies |
| `board/mt7986a-netis-nx62.dts` | board description: model, layouts, LEDs |
| `board/mt7986_netis_nx62_defconfig` | U-Boot config (single layout) |
| `board/mt7986_netis_nx62_multi_layout_defconfig` | U-Boot config (multi-layout, the one used) |
| `board/atf_mt7986_netis_nx62_defconfig` | BL2/BL31 config: DDR4, SPI-NAND without NMBM, TRNG for the stock kernel |
| `patches/` | fixes on top of upstream |
| `.github/workflows/build.yml` | GitHub Actions build |

## Building

### GitHub Actions

1. **Actions → Build Netis NX62 bootloader → Run workflow.**
2. ATF version:
   - `SP2` — ATF 2026.01.23, **recommended** (newest);
   - `2025` — ATF 2025.07.11, fallback;
   - `SP2 + 2025` — build both.
3. `upstream_ref` — leave empty (tested upstream commit) or set `master` to
   build on the latest upstream.
4. *Publish a GitHub Release* additionally creates a release with the files.
5. Result — artifact `netis_nx62-bootloader-<version>`:
   - `netis_nx62-<version>-bl2.img` — BL2 (`bl2` partition);
   - `netis_nx62-<version>-fip.bin` — BL31 + U-Boot (`fip` partition);
   - `SHA256SUMS`, `upstream-commit.txt`, the README and the build log.

### Locally (Ubuntu 24.04)

```sh
sudo apt install build-essential bc bison flex gcc-aarch64-linux-gnu \
    device-tree-compiler libssl-dev libgnutls28-dev nodejs npm python3 git
./build.sh                    # SP2, tested upstream
VERSION=2025 ./build.sh       # ATF 2025
UPSTREAM_REF=master ./build.sh
```

### Updating upstream

- The tested upstream commit is set by `UPSTREAM_PINNED` in `build.sh`.
- Every Monday the workflow tries to build on the latest upstream `master`.
  A failure means upstream changed something the patches or board files
  depend on.
- To move to a new version: build with `upstream_ref = master`, test the
  bootloader and put the commit from `upstream-commit.txt` into
  `UPSTREAM_PINNED`.

## Before flashing

> **Warning.** Replacing BL2 can brick the router. Recovery after a failure
> is only possible over UART with mtk_uartboot. Do it at your own risk.

- Flash **both** files: BL2 and FIP. The stock BL2 uses NMBM and will corrupt
  the official OpenWrt UBI.
- Back up the `bl2`, `u-boot-env`, `factory` and `fip` partitions (better:
  the whole flash). `factory` holds the Wi-Fi calibration and MAC addresses
  and is unique to each router.
- If you are on stock firmware or an NMBM build, make sure NMBM has not
  remapped any blocks (no NMBM bad/remapped block messages in `dmesg`). If
  blocks were remapped, data is not at the addresses a non-NMBM bootloader
  sees — do not flash.
- The 512 MB NAND version (Chinese market) is not supported.

## Flashing the bootloader

### From OpenWrt (official or a stock-layout build)

Copy the files to `/tmp` on the router and check the partition names with
`cat /proc/mtd` (`bl2`, `fip`; some builds use `BL2`, `FIP`). The bootloader
partitions are write-protected in OpenWrt, so the `mtd-rw` module is needed:

```sh
apk update && apk add kmod-mtd-rw        # OpenWrt 25.12
# opkg update && opkg install kmod-mtd-rw # OpenWrt 24.10 and older
insmod mtd-rw i_want_a_brick=1

cd /tmp
sha256sum netis_nx62-SP2-*            # compare with SHA256SUMS
mtd write netis_nx62-SP2-fip.bin fip && mtd verify netis_nx62-SP2-fip.bin fip
mtd write netis_nx62-SP2-bl2.img bl2 && mtd verify netis_nx62-SP2-bl2.img bl2
```

Do not reboot if `mtd verify` reports an error — write again.

### If this U-Boot is already installed

In the failsafe web UI: **U-Boot update** page — `fip.bin`, **BL2 update**
page — `bl2.img`.

### From stock firmware

Not directly: first install OpenWrt using one of the known guides (e.g.
[SevenMaxs/netis-nx62-flash-tools](https://github.com/SevenMaxs/netis-nx62-flash-tools)),
then proceed as above.

## Failsafe web UI

1. Power the router off, hold **Reset**, power it on and keep holding the
   button for a few seconds (the button is set by the `glbtn_key` variable,
   default `reset,wps,mesh`).
2. Connect the PC to a LAN port with a cable (if the page doesn't open, try
   another LAN port). The PC gets an address via DHCP, or set
   `192.168.1.2/24` manually.
3. Open **http://192.168.1.1** (or `http://failsafe.lan`).

The web UI also opens automatically if booting the firmware fails.

## Installing firmware

On the **Firmware update** page select the **layout** and the file:

| Firmware | Layout | File |
| --- | --- | --- |
| OpenWrt 24.10 / 25.12 | `openwrt` | `openwrt-…-mediatek-filogic-netcore_n60-pro-squashfs-sysupgrade.itb` |
| ImmortalWrt 24.10+ | `openwrt` | `immortalwrt-…-mediatek-filogic-netcore_n60-pro-squashfs-sysupgrade.itb` |
| Stock-layout builds (Kwrt, ImmortalWrt mt798x…) | `default` | `*-squashfs-sysupgrade.bin` (tar with `kernel` and `root`) |
| Stock from a backup | `default` | raw UBI image (`UBI#…`) taken from the stock `ubi` partition |

On a layout switch the `ubi` partition is erased and recreated, and the
selected layout is saved to the U-Boot environment only after a successful
write. The `factory` partition is never touched.

An initramfs (e.g. OpenWrt `…-initramfs-recovery.itb`) can be booted from RAM
on the **Load initramfs** page, without writing to flash.

### Switching the layout without reflashing

If firmware for the desired layout is already on the flash (e.g. you replaced
the bootloader on a router running official OpenWrt), set `mtd_layout` =
`openwrt` (or `default`) on the **Environment** page, save and reboot. From
the U-Boot console:

```
setenv mtd_layout openwrt; setenv mtd_layout_label openwrt; saveenv; reset
```

Until the variable is set, the `default` layout is used. On a flash with
official OpenWrt, U-Boot with the `default` layout simply fails to attach UBI
(it is larger than the partition) and opens the web UI — no data is changed.

## Going back from `openwrt` to stock

The stock kernel looks for the NMBM tables in the last 8 MB of the flash,
while official OpenWrt uses that area for UBI. After OpenWrt the NMBM tables
are gone, and stock firmware only boots if its kernel can recreate NMBM. The
reliable way back is a **full flash backup taken while on stock** (**Backup**
page), restored completely via **Flash** or UART. Stock-layout builds (Kwrt,
ImmortalWrt mt798x) usually create NMBM themselves.

## Credits and license

- [Yuzhii0718/bl-mt798x-dhcpd](https://github.com/Yuzhii0718/bl-mt798x-dhcpd)
  (based on hanwckf's bl-mt798x) — ATF, U-Boot, DHCP server and web UI.
- [OpenWrt](https://github.com/openwrt/openwrt) — NX62 / N60 Pro DTS and
  flash layout.

GPL-2.0, see [LICENSE](LICENSE).
