#!/bin/bash
# Netis NX62 / Netcore N60 Pro bootloader (BL2 + FIP), multi-layout, no NMBM.
#
# Fetches upstream bl-mt798x-dhcpd, adds the NX62 board files from board/,
# applies patches/*.patch, builds and verifies the images.
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
UPSTREAM_PINNED=b1aa9810e860f36a1f2cce474ce3b220e2e1e99c

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

step "Add Netis NX62 board files"
cp "$TOP/board/mt7986a-netis-nx62.dts" "$SRC/$UBOOT_DIR/arch/arm/dts/"
cp "$TOP/board/mt7986_netis_nx62_defconfig" \
   "$TOP/board/mt7986_netis_nx62_multi_layout_defconfig" \
   "$SRC/$UBOOT_DIR/configs-nonmbm/"
for d in atf-20250711 atf-20260123; do
	cp "$TOP/board/atf_mt7986_netis_nx62_defconfig" \
	   "$SRC/$d/configs-nonmbm/mt7986_netis_nx62_defconfig"
done

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
	BOARD=netis_nx62 VERSION="$VERSION" VARIANT=nonmbm \
	MULTI_LAYOUT=1 FIXED_MTDPARTS=1 SILENT=Y ./build.sh
)

step "Verify"
bl2=$(ls "$SRC"/output/bl2-mt7986_netis_nx62_"$VERSION"-nonmbm_*.img)
fip=$(ls "$SRC"/output/fip-mt7986_netis_nx62_"$VERSION"-*-nonmbm-fixed-parts-multi-layout_*.bin)
atf_cfg="$SRC/$ATF_DIR/build/.config"
uboot_cfg="$SRC/$UBOOT_DIR/.config"

fail() { echo "VERIFY FAILED: $*" >&2; exit 1; }
[ "$(stat -c%s "$bl2")" -le $((1024 * 1024)) ] || fail "BL2 larger than the 1 MiB bl2 partition"
[ "$(stat -c%s "$fip")" -le $((2048 * 1024)) ] || fail "FIP larger than the 2 MiB fip partition"
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
