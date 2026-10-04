# Netis NX62 / Netcore N60 Pro: multi-layout bootloader

**English** | [Русский](README.ru.md)

BL2 + FIP (BL31 + U-Boot with a DHCP server and a failsafe web UI) for the
**Netis NX62** (hardware twin of the **Netcore N60 Pro**): MT7986A, DDR4
512 MB / 1 GB / 2 GB, 128 MB SPI-NAND (2 KB page, 128 KB block).

The web UI shows the device as **Netis NX62**. The bootloader supports two
flash layouts and switches between them when you flash firmware:

| Layout (`mtd_layout`) | Firmware | `ubi` partition |
| --- | --- | --- |
| `default` | stock Netis/Netcore firmware; builds on the stock NMBM layout (Kwrt, ImmortalWrt mt798x, etc.) | `117248k` (0x580000–0x7800000) |
| `openwrt` | official OpenWrt 24.10 / 25.12 and ImmortalWrt 24.10+, device `netcore_n60-pro` | `125440k` (0x580000–0x8000000) |

The start of the flash is the same for both layouts:
`1024k(bl2),512k(u-boot-env),2048k(factory),2048k(fip)`.

## Why earlier builds were unstable

1. **NMBM.** The stock firmware uses NMBM: its management tables live in the
   last 8 MB of the flash. Official OpenWrt does not use NMBM and uses the
   flash up to the end. A bootloader with NMBM (the `default` variant of
   upstream, and the stock BL2) looks for these tables **on every boot** and,
   if it can't find them, writes new ones at the end of the flash — right on
   top of the official OpenWrt UBI blocks. That causes random UBI errors.
   This build (`nonmbm` variant) accesses the NAND directly, like the official
   OpenWrt bootloader: BL2 skips bad blocks (`_NAND_SKIP_BAD`), U-Boot uses
   `spi-nand0`. The `default` layout never touches the NMBM area, so the stock
   kernel keeps working with its tables.
2. **Wrong layout in the DTS.** The previous attempt had
   `factory_part = "factory"`. That is the partition *the web UI writes the
   firmware to*, so the firmware would have overwritten the Wi-Fi calibration.
   Also, `ubi` was `-(ubi)` on top of NMBM, and `sysupgrade_rootfs_ubipart`
   pointed to a non-existent `rootfs_data` partition.
3. **Layout switch while UBI is attached.** If UBI was already attached (e.g.
   after a failed boot attempt), U-Boot could not recreate the partitions of
   the new layout and wrote the firmware into the old `ubi` partition. Now UBI
   is detached on a layout switch, and the `ubi` partition of the new layout
   is erased before writing — nothing of the old layout survives.
4. **TRNG.** ATF 2025/2026 restricts the hardware random number generator to
   the secure world (access only via SMC). The stock kernel 5.4 reads the TRNG
   registers directly and gets hwrng errors. For the NX62 the
   `_MT7986_TRNG_NS_ACCESS` option is enabled: both direct access (stock) and
   SMC (OpenWrt) work.
5. **Outdated sources.** The fork was 482 commits behind upstream. Now the
   sources are taken directly from the current upstream
   [Yuzhii0718/bl-mt798x-dhcpd](https://github.com/Yuzhii0718/bl-mt798x-dhcpd)
   (new SPI-NAND drivers, failsafe and TCP stack fixes). The previous full
   source tree is kept in the `old-full-tree` branch.

## Repository layout

Only the NX62-specific files live here. The U-Boot and ATF sources are
downloaded from upstream
[Yuzhii0718/bl-mt798x-dhcpd](https://github.com/Yuzhii0718/bl-mt798x-dhcpd)
at build time.

| File | Purpose |
| --- | --- |
| `build.sh` | fetches upstream, adds the NX62 files, applies the patches, builds and verifies |
| `board/mt7986a-netis-nx62.dts` | board description: model "Netis NX62", `default` and `openwrt` layouts, LEDs |
| `board/mt7986_netis_nx62_defconfig` | U-Boot config (single layout) |
| `board/mt7986_netis_nx62_multi_layout_defconfig` | U-Boot config (multi-layout, the one used) |
| `board/atf_mt7986_netis_nx62_defconfig` | BL2/BL31 config: DDR4, SPI-NAND without NMBM, TRNG for the stock kernel |
| `patches/0001-…TRNG…patch` | ATF: option to let the stock kernel access the TRNG |
| `patches/0002-…UBI…patch` | U-Boot: clean UBI rebuild on layout switch |
| `.github/workflows/build.yml` | GitHub Actions build |

## Building with GitHub Actions

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
   - `SHA256SUMS`, `upstream-commit.txt`, the README in both languages and
     the build log.

The build verifies its own output: BL2 and U-Boot without NMBM, both layouts
present, model `Netis NX62`, image sizes, no layout writing firmware to a
foreign partition. If anything is wrong, the build fails instead of producing
an image.

Locally (Ubuntu 24.04):

```sh
sudo apt install build-essential bc bison flex gcc-aarch64-linux-gnu \
    device-tree-compiler libssl-dev libgnutls28-dev nodejs npm python3 git
./build.sh                    # SP2, tested upstream
VERSION=2025 ./build.sh       # ATF 2025
UPSTREAM_REF=master ./build.sh
```

## Updating upstream

- Every Monday the workflow tries to build the NX62 on the latest upstream
  `master`. If it fails, upstream changed something that needs fixing in the
  patches or board files.
- To move to a new version: run the build with `upstream_ref = master`, test
  the bootloader and put the commit from `upstream-commit.txt` into
  `UPSTREAM_PINNED` in `build.sh`.
- There are no merge conflicts with upstream: the repository only contains
  its own files.

## Before flashing

> **Warning.** Replacing BL2 can brick the router. Recovery after a failure
> is only possible over UART with mtk_uartboot. Do it at your own risk. The
> build has been verified by compilation and static checks, not on real
> hardware.

- Flash **both** files: BL2 and FIP. The stock BL2 (and the BL2 of the
  `default` variant) uses NMBM and will corrupt the official OpenWrt UBI.
- Back up the `bl2`, `u-boot-env`, `factory` and `fip` partitions (better:
  the whole flash). `factory` holds the Wi-Fi calibration and MAC addresses
  and is unique to each router.
- If you are on stock firmware or an NMBM build, make sure NMBM has not
  remapped any blocks (no NMBM bad/remapped block messages in `dmesg`). If
  blocks were remapped, data is not at the addresses a non-NMBM bootloader
  sees — do not flash.
- The 512 MB NAND version (Chinese market) is not supported by this build.

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

### If U-Boot from this repository is already installed

In the failsafe web UI: **U-Boot update** page — `fip.bin`, **BL2 update**
page — `bl2.img`.

### From stock firmware

Not directly: first install OpenWrt using one of the known guides (e.g.
[SevenMaxs/netis-nx62-flash-tools](https://github.com/SevenMaxs/netis-nx62-flash-tools)),
then proceed as above.

## Entering the failsafe web UI

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
`openwrt` (or `default`) on the **Environment** page of the web UI, save and
reboot. From the U-Boot console:

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
reliable way back is therefore a **full flash backup taken while on stock**
(**Backup** page), restored completely via **Flash** or UART. Stock-layout
builds (Kwrt, ImmortalWrt mt798x) usually create NMBM themselves.

## Checking the Wi-Fi calibration (`factory` partition)

On OpenWrt:

```sh
cat /proc/mtd                      # index of the "factory" partition, e.g. mtd2
dd if=/dev/mtd2 of=/tmp/factory.bin
ls -l /tmp/factory.bin             # 2097152 bytes
hexdump -C -n 16 /tmp/factory.bin  # starts with "86 79" (MT7986), not "ff ff"
hexdump -C -s 0x1fef20 -n 12 /tmp/factory.bin   # two MAC addresses, not ff
dmesg | grep -i eeprom             # "use default bin" = calibration missing
cmp /tmp/factory.bin /tmp/factory-backup.bin && echo IDENTICAL
```

From a whole-flash backup (exactly 134217728 bytes) the partition is extracted
with:
`dd if=full.bin of=/tmp/factory-backup.bin bs=64k skip=24 count=32`.

Restore only if it differs and the backup is valid (2097152 bytes, starts
with `86 79`):

```sh
apk update && apk add kmod-mtd-rw     # OpenWrt 24.10: opkg update && opkg install kmod-mtd-rw
insmod mtd-rw i_want_a_brick=1
mtd write /tmp/factory-backup.bin factory
```
