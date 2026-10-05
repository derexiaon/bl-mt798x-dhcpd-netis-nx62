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
| `openwrt` | official OpenWrt 25.12+ and ImmortalWrt 24.10+, device `netcore_n60-pro` | `125440k` (0x580000–0x8000000) |

The start of the flash is the same for both layouts:
`1024k(bl2),512k(u-boot-env),2048k(factory),2048k(fip)`.

The board `netis_nx62` is part of
[Yuzhii0718/bl-mt798x-dhcpd](https://github.com/Yuzhii0718/bl-mt798x-dhcpd).
This repository builds it from upstream with two failsafe fixes that are not
merged upstream yet; the upstream sources are downloaded at build time.

## The `netis_nx62` board (in upstream)

- **No NMBM.** BL2 skips bad blocks (`_NAND_SKIP_BAD`) and U-Boot works on
  the raw `spi-nand0`, like the official OpenWrt bootloader. `netcore_n60-pro`
  (default variant) uses NMBM: on every boot it looks for the NMBM tables in
  the last 8 MB of the flash and writes new ones if they are missing, i.e. over
  the UBI blocks of official OpenWrt, which uses the flash up to the end.
- **Two layouts** (`default` and `openwrt`, see above). The `default` layout
  never touches the NMBM area, so the stock kernel keeps its NMBM tables.
- **TRNG for the stock kernel.** ATF 2025/2026 restricts the hardware random
  number generator to the secure world (SMC only); the stock kernel 5.4 reads
  the TRNG registers directly and gets hwrng errors. `_MT7986_TRNG_NS_ACCESS`
  (enabled for NX62) keeps both direct access (stock) and SMC (OpenWrt)
  working.
- The web UI shows the model as **Netis NX62**; LEDs match the OpenWrt DTS.

With upstream alone: `BOARD=netis_nx62 MULTI_LAYOUT=1 ./build.sh`.

## What this repository adds

**Fixes (patches, not merged upstream yet)**

- `0001` — **Clean layout switch.** If UBI is still attached to the old
  layout (for example after a failed boot attempt), upstream U-Boot cannot
  recreate the partitions and writes the firmware into the old `ubi`
  partition. With the patch, UBI is detached on a layout switch, and the `ubi`
  partition of the new layout is erased before writing.
- `0002` — **Layout list starts at the current layout.** In upstream the
  layout list on the firmware page always starts at the first layout, so
  flashing without touching it silently switches to `default`. With the patch
  the layout in use is preselected (all web UI themes).

**Build checks**

The build fails instead of producing an image if BL2 or U-Boot is built with
NMBM, the BL2 header doesn't match the NX62 NAND (2 KB page, 64 B spare — same
as the stock BL2), a layout is missing, the model is wrong, an image doesn't
fit its partition, or a layout writes firmware to a partition other than `ubi`.

## Repository layout

| File | Purpose |
| --- | --- |
| `build.sh` | fetches upstream, applies the patches, builds and verifies |
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
4. *Publish a GitHub Release* additionally creates a release with the files
   (plus `netis_nx62-<version>.zip` with both images, for forums that don't
   accept `.bin`/`.img`);
   *Delete older releases* removes the previous ones.
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
  A failure usually means upstream merged the patches (then delete them) or
  changed the code they touch.
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
# opkg update && opkg install kmod-mtd-rw # opkg-based builds (ImmortalWrt 24.10, etc.)
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

The stock firmware is OpenWrt-based (MediaTek SDK) and has SSH (user
`useradmin`, the password set in the web UI). The `BL2` partition is
read-only there, but the whole-flash device `spi0.1` (mtd0) is writable, and
BL2 lives at its very beginning. So both files are written right from stock:

```sh
cat /proc/mtd           # expect: spi0.1 08000000, BL2, u-boot-env, Factory, FIP, ubi
dmesg | grep -i nmbm    # no remapped/bad block messages
# back up everything first, e.g.:
dd if=/dev/mtd0 | gzip > /tmp/mtd0_spi.bin.gz   # copy it to the PC (scp -O / WinSCP)

cd /tmp
ls -l netis_nx62-SP2-bl2.img          # ~150 KB — this one goes to spi0.1
sha256sum netis_nx62-SP2-*            # compare with SHA256SUMS
mtd write netis_nx62-SP2-bl2.img spi0.1
mtd write netis_nx62-SP2-fip.bin FIP && mtd verify netis_nx62-SP2-fip.bin FIP
reboot
```

> **Only the BL2 image goes to `spi0.1`.** `spi0.1` is the whole flash: a
> wrong or larger file written there overwrites `u-boot-env` and `Factory`
> (the Wi-Fi calibration).

After the reboot the stock firmware keeps booting with the `default` layout;
OpenWrt can be installed from the failsafe web UI (layout `openwrt`).

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

On the **Firmware update** page choose the file and the layout in the
**Choose mtd layout** list (it shows `default` and `openwrt`, the layout in
use is preselected):

| Firmware | Layout | File |
| --- | --- | --- |
| OpenWrt 25.12+ | `openwrt` | `openwrt-…-mediatek-filogic-netcore_n60-pro-squashfs-sysupgrade.itb` |
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
official OpenWrt, U-Boot with the `default` layout fails to attach UBI (it is
larger than the partition) and opens the web UI; the firmware is not
damaged — the normal boot path only reads UBI.

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
