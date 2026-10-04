#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
collect_mtd_layout.py
Collect MTK partition tables for MT798* boards and export the summary as Markdown.

Modes:
- default: single-layout partition tables stored in CONFIG_MTDPARTS_DEFAULT
- multi_layout: partition tables stored in device tree mtd-layout nodes
- ubootmod: partition tables stored in CONFIG_MTDPARTS_DEFAULT from configs-fit/

Boards with CONFIG_MTK_BOOTMENU_MMC=y are skipped.

Usage:
    python collect_mtd_layout.py [uboot_root] [dts_root] [output_filename]

Default paths are relative to this script location.
"""
from __future__ import annotations

import datetime
import os
import re
import sys
from typing import Dict, List, Optional, Tuple


PLATFORMS = ["mt7981", "mt7986", "mt7987", "mt7988"]
CONFIG_DIRS = [
    ("configs", "default"),
    ("configs-nonmbm", "nonmbm"),
    ("configs-fit", "ubootmod"),
]
DEFAULT_OUTPUT = "mtd_layout_summary.md"
MODE_ORDER = ["default", "nonmbm", "multi_layout", "ubootmod"]


def normalize_platform(name: str) -> str:
    m = re.match(r"^(mt798[1678])", name.lower())
    return m.group(1) if m else name.lower()


def parse_config_name(filename: str) -> Tuple[str, str]:
    stem = filename[:-len("_defconfig")] if filename.endswith("_defconfig") else filename
    parts = stem.split("_", 1)
    platform = normalize_platform(parts[0]) if parts else ""
    model = parts[1] if len(parts) > 1 else ""
    if model.endswith("_multi_layout"):
        model = model[: -len("_multi_layout")]
    return platform, model


def parse_dts_name(filename: str) -> Tuple[str, str]:
    stem = filename[:-4] if filename.endswith(".dts") else filename[:-5] if filename.endswith(".dtsi") else filename
    if stem.startswith("."):
        stem = stem[1:]
    parts = re.split(r"[-_]", stem, maxsplit=1)
    platform = normalize_platform(parts[0]) if parts else ""
    model = parts[1] if len(parts) > 1 else ""
    return platform, model


def read_text(filepath: str) -> str:
    actual_filepath = os.path.realpath(filepath)
    try:
        with open(actual_filepath, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        with open(actual_filepath, "rb") as f:
            return f.read().decode("utf-8", errors="ignore")


def extract_config_value(content: str, key: str) -> Optional[str]:
    m = re.search(rf'^%s="([^"]*)"$' % re.escape(key), content, re.MULTILINE)
    return m.group(1) if m else None


def extract_dts_string(content: str, key: str) -> Optional[str]:
    m = re.search(rf'^\s*{re.escape(key)}\s*=\s*"([^"]*)"\s*;?\s*$', content, re.MULTILINE)
    return m.group(1) if m else None


def has_config_flag(content: str, key: str) -> bool:
    return f"{key}=y" in content


def parse_config(filepath: str, mode: str) -> Optional[Dict[str, str]]:
    content = read_text(filepath)
    if has_config_flag(content, "CONFIG_MTK_BOOTMENU_MMC"):
        return None

    platform, model = parse_config_name(os.path.basename(filepath))
    if platform not in PLATFORMS:
        return None

    # Check if this is a multi_layout config
    is_multi_layout = (
        has_config_flag(content, "CONFIG_MEDIATEK_MULTI_MTD_LAYOUT")
        or os.path.basename(filepath).endswith("_multi_layout_defconfig")
    )
    
    # Collect multi_layout only from "configs" (default mode)
    if is_multi_layout:
        if mode == "default":
            mode = "multi_layout"
        elif mode != "ubootmod":
            # Skip multi_layout from nonmbm mode
            return None

    mtdparts = extract_config_value(content, "CONFIG_MTDPARTS_DEFAULT")
    if not mtdparts:
        return None

    return {
        "source": os.path.basename(filepath),
        "platform": platform,
        "model": model or "-",
        "mode": mode,
        "mtdids": extract_config_value(content, "CONFIG_MTDIDS_DEFAULT") or "-",
        "mtdparts": mtdparts,
        "default_fdt_file": extract_config_value(content, "CONFIG_DEFAULT_FDT_FILE") or "-",
    }


def find_matching_brace(text: str, open_brace_index: int) -> int:
    depth = 0
    in_string = False
    escaped = False
    for idx in range(open_brace_index, len(text)):
        ch = text[idx]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return idx
    return -1


def extract_block(text: str, start_pattern: str) -> List[str]:
    blocks: List[str] = []
    pattern = re.compile(start_pattern, re.MULTILINE)
    for match in pattern.finditer(text):
        open_brace_index = match.end() - 1
        if open_brace_index < 0 or text[open_brace_index] != "{":
            continue
        close_brace_index = find_matching_brace(text, open_brace_index)
        if close_brace_index == -1:
            continue
        blocks.append(text[open_brace_index + 1 : close_brace_index])
    return blocks


def parse_layout_block(block: str) -> Dict[str, str]:
    return {
        "label": extract_dts_string(block, "label") or "-",
        "mtdids": extract_dts_string(block, "mtdids") or "-",
        "mtdparts": extract_dts_string(block, "mtdparts") or "-",
        "boot_part": extract_dts_string(block, "boot_part") or "-",
        "factory_part": extract_dts_string(block, "factory_part") or "-",
        "sysupgrade_kernel_ubipart": extract_dts_string(block, "sysupgrade_kernel_ubipart") or "-",
        "sysupgrade_rootfs_ubipart": extract_dts_string(block, "sysupgrade_rootfs_ubipart") or "-",
    }


def parse_mtd_layout_dts(filepath: str) -> Optional[Dict[str, object]]:
    content = read_text(filepath)
    if "mtd-layout" not in content:
        return None

    platform, model = parse_dts_name(os.path.basename(filepath))
    if platform not in PLATFORMS:
        return None

    mtd_layout_blocks: List[Dict[str, str]] = []
    for layout_container in extract_block(content, r"mtd-layout\s*{"):
        for layout_block in extract_block(layout_container, r"layout@[^\s{]+\s*{"):
            mtd_layout_blocks.append(parse_layout_block(layout_block))

    if not mtd_layout_blocks:
        return None

    return {
        "source": os.path.basename(filepath),
        "platform": platform,
        "model": model or "-",
        "mode": "multi_layout",
        "layouts": mtd_layout_blocks,
    }


def collect_configs(uboot_root: str) -> List[Dict[str, str]]:
    results: List[Dict[str, str]] = []
    for dir_name, mode in CONFIG_DIRS:
        config_dir = os.path.join(uboot_root, dir_name)
        if not os.path.isdir(config_dir):
            continue
        try:
            names = sorted(os.listdir(config_dir))
        except Exception as e:
            print(f"Error accessing directory {config_dir}: {e}", file=sys.stderr)
            continue

        for fn in names:
            if not fn.endswith("_defconfig"):
                continue
            if not fn.startswith(tuple(PLATFORMS)):
                continue
            fp = os.path.join(config_dir, fn)
            if not (os.path.isfile(fp) or os.path.islink(fp)):
                continue
            try:
                entry = parse_config(fp, mode)
                if entry:
                    entry["source"] = os.path.relpath(fp, uboot_root)
                    results.append(entry)
            except Exception as e:
                print(f"Error parsing file {fp}: {e}", file=sys.stderr)
    return results


def collect_dts(dts_root: str) -> List[Dict[str, object]]:
    results: List[Dict[str, object]] = []
    for root, _, files in os.walk(dts_root):
        for fn in sorted(files):
            if not (fn.endswith(".dts") or fn.endswith(".dtsi")):
                continue
            if not fn.startswith(tuple(PLATFORMS)):
                continue
            fp = os.path.join(root, fn)
            if not (os.path.isfile(fp) or os.path.islink(fp)):
                continue
            try:
                entry = parse_mtd_layout_dts(fp)
                if entry:
                    entry["source"] = os.path.relpath(fp, dts_root)
                    results.append(entry)
            except Exception as e:
                print(f"Error parsing file {fp}: {e}", file=sys.stderr)
    return results


def group_by_platform(entries: List[Dict[str, object]]) -> Dict[str, Dict[str, List[Dict[str, object]]]]:
    grouped: Dict[str, Dict[str, List[Dict[str, object]]]] = {p: {m: [] for m in MODE_ORDER} for p in PLATFORMS}
    for entry in entries:
        platform = entry.get("platform", "")
        mode = entry.get("mode", "")
        if platform in grouped and mode in grouped[platform]:
            grouped[platform][mode].append(entry)
    return grouped


def fmt_path(path: str) -> str:
    return f"`{path}`"


def render_config_table(lines: List[str], entries: List[Dict[str, object]], mode: str) -> None:
    if not entries:
        lines.append("No data.\n\n")
        return

    lines.append("| Source | Model | MTDIDS | MTDPARTS_DEFAULT | FDT |\n")
    lines.append("|---|---|---|---|---|\n")
    for entry in sorted(entries, key=lambda e: (str(e.get("source", "")), str(e.get("model", "")))):
        lines.append(
            f"| {fmt_path(str(entry['source']))} | {entry['model']} | {entry['mtdids']} | {entry['mtdparts']} | {entry.get('default_fdt_file', '-') } |\n"
        )
    lines.append("\n")


def render_multi_layout_table(lines: List[str], entries: List[Dict[str, object]]) -> None:
    if not entries:
        lines.append("No data.\n\n")
        return

    lines.append("| Source | Model | Layout | MTDIDS | MTDPARTS | Boot Part | Factory Part | Sysupgrade Kernel | Sysupgrade Rootfs |\n")
    lines.append("|---|---|---|---|---|---|---|---|---|\n")
    for entry in sorted(entries, key=lambda e: (str(e.get("source", "")), str(e.get("model", "")))):
        layouts = entry.get("layouts", [])
        first = True
        for layout in layouts:
            source = fmt_path(str(entry["source"])) if first else ""
            model = entry["model"] if first else ""
            first = False
            lines.append(
                f"| {source} | {model} | {layout['label']} | {layout['mtdids']} | {layout['mtdparts']} | {layout['boot_part']} | {layout['factory_part']} | {layout['sysupgrade_kernel_ubipart']} | {layout['sysupgrade_rootfs_ubipart']} |\n"
            )
    lines.append("\n")


def render_md(entries: List[Dict[str, object]], outpath: str) -> str:
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: List[str] = []
    lines.append("# MT798 MTD Layout Summary\n\n")
    lines.append(f"Generated: {now}\n\n")
    lines.append(
        "This document collects MTK partition tables from configs and device-tree `mtd-layout` nodes.\n\n"
    )
    lines.append("Boards with `CONFIG_MTK_BOOTMENU_MMC=y` are skipped.\n\n")

    grouped = group_by_platform(entries)
    for platform in PLATFORMS:
        lines.append(f"## {platform.upper()} Platform\n\n")

        for mode in MODE_ORDER:
            lines.append(f"### {mode}\n\n")
            mode_entries = grouped[platform][mode]
            if mode == "multi_layout":
                render_multi_layout_table(lines, mode_entries)
            else:
                render_config_table(lines, mode_entries, mode)

    with open(outpath, "w", encoding="utf-8") as f:
        f.writelines(lines)

    return outpath


def main() -> None:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_uboot_root = os.path.join(script_dir, "..", "uboot-mtk-20250711")
    default_dts_root = os.path.join(default_uboot_root, "arch", "arm", "dts")
    default_output_dir = os.path.join(script_dir, "..", "document")
    default_outname = DEFAULT_OUTPUT

    uboot_root = default_uboot_root
    dts_root = default_dts_root
    outname = default_outname

    if len(sys.argv) >= 2:
        uboot_root = sys.argv[1]
    if len(sys.argv) >= 3:
        dts_root = sys.argv[2]
    if len(sys.argv) >= 4:
        outname = sys.argv[3]

    entries: List[Dict[str, object]] = []
    entries.extend(collect_configs(uboot_root))
    entries.extend(collect_dts(dts_root))

    outpath = os.path.join(default_output_dir, outname)
    render_md(entries, outpath)
    print(f"Exported to: {outpath}, processed {len(entries)} layout records.")


if __name__ == "__main__":
    main()
