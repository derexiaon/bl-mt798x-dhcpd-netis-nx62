#!/bin/bash
# Netis NX62 / Netcore N60 Pro bootloader (BL2 + FIP), multi-layout, no NMBM.
#
# The board (netis_nx62) is part of upstream bl-mt798x-dhcpd. This script
# fetches upstream, applies patches/*.patch (fixes not merged upstream yet),
# builds and verifies the images.
#
# Usage:
#   ./build.sh                      # ATF 2026.01.23 (SP2), pinned upstream
#   VERSION=2025 ./build.sh         # ATF 2025.07.11
#   UPSTREAM_REF=master ./build.sh  # latest upstream instead of the pinned one
#
# Output: output/netis_nx62-<VERSION>-{bl2.img,fip.bin}, SHA256SUMS

set -euo pipefail

# Tested upstream commit. To update: build with UPSTREAM_REF=master, check the
# result and put the new commit here.
UPSTREAM_PINNED=43baf20d213a868a20efca36fbd24d1b8c12b909

UPSTREAM_URL="${UPSTREAM_URL:-https://github.com/Yuzhii0718/bl-mt798x-dhcpd}"
UPSTREAM_REF="${UPSTREAM_REF:-$UPSTREAM_PINNED}"
VERSION="${VERSION:-SP2}"

TOP="$(cd "$(dirname "$0")" && pwd)"
SRC="$TOP/src"
OUT="$TOP/output"

case "$VERSION" in
	SP2) ATF_DIR=atf-20260123 ;;
	2025) ATF_DIR=atf-20250711 ;;
	*) echo "VERSION must be SP2 or 2025" >&2; exit 1 ;;
esac
UBOOT_DIR=uboot-mtk-20250711

step() { echo; echo "=== $* ==="; }

step "Fetch upstream $UPSTREAM_URL @ $UPSTREAM_REF"
rm -rf "$SRC"
git init -q "$SRC"
git -C "$SRC" fetch -q --depth 1 "$UPSTREAM_URL" "$UPSTREAM_REF"
git -C "$SRC" checkout -q FETCH_HEAD
UPSTREAM_SHA="$(git -C "$SRC" rev-parse HEAD)"
echo "upstream commit: $UPSTREAM_SHA"

step "Apply patches"
for p in "$TOP"/patches/*.patch; do
	echo "$(basename "$p")"
	git -C "$SRC" apply --check "$p" || {
		echo "Patch $(basename "$p") does not apply to upstream $UPSTREAM_SHA" >&2
		exit 1
	}
	git -C "$SRC" apply "$p"
done

step "Build (VERSION=$VERSION)"
(
	cd "$SRC"
	BOARD=netis_nx62 VERSION="$VERSION" VARIANT=default \
	MULTI_LAYOUT=1 FIXED_MTDPARTS=1 SILENT=Y ./build.sh
)

step "Verify"
bl2=$(ls "$SRC"/output/bl2-mt7986_netis_nx62_"$VERSION"_md5-*.img)
fip=$(ls "$SRC"/output/fip-mt7986_netis_nx62_"$VERSION"-*-fixed-parts-multi-layout_md5-*.bin)
atf_cfg="$SRC/$ATF_DIR/build/.config"
uboot_cfg="$SRC/$UBOOT_DIR/.config"

fail() { echo "VERIFY FAILED: $*" >&2; exit 1; }
[ "$(stat -c%s "$bl2")" -le $((1024 * 1024)) ] || fail "BL2 larger than the 1 MiB bl2 partition"
[ "$(stat -c%s "$fip")" -le $((2048 * 1024)) ] || fail "FIP larger than the 2 MiB fip partition"
# BootROM header must match the NX62 SPI-NAND (and the stock BL2):
# "SPINAND!", 2048-byte page, 64-byte spare
[ "$(head -c 8 "$bl2")" = "SPINAND!" ] || fail "BL2 has no SPI-NAND BootROM header"
[ "$(od -An -tu4 -j16 -N8 "$bl2" | tr -s ' ')" = " 2048 64" ] || fail "BL2 header is not for 2K page / 64B spare NAND"
grep -q '^_NAND_SKIP_BAD=y' "$atf_cfg" || fail "BL2 is not built with skip-bad"
grep -q '^NMBM=1' "$atf_cfg" && fail "BL2 is built with NMBM"
grep -q '^MT7986_TRNG_NS_ACCESS=1' "$atf_cfg" || fail "TRNG access for the stock kernel is off"
grep -q '^CONFIG_MEDIATEK_MULTI_MTD_LAYOUT=y' "$uboot_cfg" || fail "U-Boot without multi-layout"
grep -q '^CONFIG_ENABLE_NAND_NMBM=y' "$uboot_cfg" && fail "U-Boot is built with NMBM"
dts=$(dtc -I dtb -O dts "$SRC/$UBOOT_DIR/dts/dt.dtb" 2>/dev/null)
grep -q 'model = "Netis NX62"' <<<"$dts" || fail "wrong board model"
grep -q '117248k(ubi)' <<<"$dts" || fail "layout 'default' missing"
grep -q '125440k(ubi)' <<<"$dts" || fail "layout 'openwrt' missing"
grep -q 'factory_part' <<<"$dts" && fail "a layout writes firmware to a custom partition"
echo "OK"

mkdir -p "$OUT"
cp "$bl2" "$OUT/netis_nx62-$VERSION-bl2.img"
cp "$fip" "$OUT/netis_nx62-$VERSION-fip.bin"
echo "$UPSTREAM_SHA" > "$OUT/upstream-commit.txt"
(cd "$OUT" && sha256sum *.img *.bin > SHA256SUMS && cat SHA256SUMS)
