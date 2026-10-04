#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
collect_button.py
Collect MT798* device-tree files containing `compatible = "gpio-keys";`
and export button definitions as Markdown.

Each entry records:
- board filename
- model name
- button label
- pio number
- active level (LOW/HIGH)

Usage:
    python collect_button.py [dts_dir] [output_filename]
    python collect_button.py [dts_dir] [output_filename] --recursive

Note: Supports both regular files and symbolic links.
"""
import datetime
import os
import re
import sys


PLATFORMS = ["mt7981", "mt7986", "mt7987", "mt7988"]
DEFAULT_OUTPUT_NAME = "button_summary.md"


def _real_read_text(filepath):
    actual_filepath = os.path.realpath(filepath)

    try:
        with open(actual_filepath, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        with open(actual_filepath, "rb") as f:
            return f.read().decode("utf-8", errors="ignore")


def _detect_platform(filename):
    name = filename.lower()
    for platform in PLATFORMS:
        if name.startswith(platform):
            return platform
    return None


def _board_model_from_filename(filename):
    name = os.path.splitext(filename)[0]
    m = re.match(r"^(mt798[1-8][a-z]?)[-_](.+)$", name)
    if m:
        return m.group(2)
    return name


def _strip_comments(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"//.*?$", "", text, flags=re.M)
    return text


def _find_matching_brace(text, open_brace_index):
    depth = 0
    for idx in range(open_brace_index, len(text)):
        ch = text[idx]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return idx
    return -1


def _parse_gpio_spec(spec):
    # Examples:
    #   <&pio 14 GPIO_ACTIVE_LOW>
    #   <&pio 7 GPIO_ACTIVE_HIGH>
    m = re.search(r"<&\s*pio\s+(\d+)\s+GPIO_ACTIVE_(LOW|HIGH)\s*>", spec)
    if not m:
        return None
    return {
        "pio": m.group(1),
        "level": m.group(2),
    }


def _parse_gpio_keys_blocks(content):
    """Return parsed button entries from gpio-keys nodes."""
    entries = []
    cleaned = _strip_comments(content)
    pos = 0

    while True:
        key_pos = cleaned.find('compatible = "gpio-keys";', pos)
        if key_pos < 0:
            break

        # Search backwards for the nearest '{' that starts the gpio-keys node.
        brace_pos = cleaned.rfind("{", 0, key_pos)
        if brace_pos < 0:
            pos = key_pos + 1
            continue

        node_end = _find_matching_brace(cleaned, brace_pos)
        if node_end < 0:
            pos = key_pos + 1
            continue

        block = cleaned[brace_pos + 1:node_end]

        # Find direct child nodes with a label and gpios property.
        child_pos = 0
        while True:
            label_pos = block.find("label =", child_pos)
            if label_pos < 0:
                break

            # find node start brace before label
            node_open = block.rfind("{", 0, label_pos)
            if node_open < 0:
                child_pos = label_pos + 1
                continue

            node_close = _find_matching_brace(block, node_open)
            if node_close < 0:
                child_pos = label_pos + 1
                continue

            node_text = block[node_open + 1:node_close]

            label_m = re.search(r'label\s*=\s*"([^"]+)"\s*;', node_text)
            gpio_m = re.search(r'gpios\s*=\s*(<[^;>]+>)\s*;', node_text)
            if label_m and gpio_m:
                gpio_info = _parse_gpio_spec(gpio_m.group(1))
                if gpio_info:
                    entries.append({
                        "label": label_m.group(1),
                        "pio": gpio_info["pio"],
                        "level": gpio_info["level"],
                    })

            child_pos = node_close + 1

        pos = node_end + 1

    return entries


def parse_device_tree_file(filepath, display_path):
    content = _real_read_text(filepath)
    filename = os.path.basename(filepath)
    platform = _detect_platform(filename)
    if not platform:
        return None

    buttons = _parse_gpio_keys_blocks(content)
    if not buttons:
        return None

    model = _board_model_from_filename(filename)
    return {
        "filename": filename,
        "path": display_path,
        "platform": platform,
        "model": model,
        "buttons": buttons,
    }


def collect(dirpath, recursive=False):
    results = []

    if recursive:
        iterator = []
        for root, _dirs, files in os.walk(dirpath):
            for fn in files:
                iterator.append((root, fn))
    else:
        iterator = [(dirpath, fn) for fn in sorted(os.listdir(dirpath))]

    for root, fn in iterator:
        if not (fn.endswith(".dts") or fn.endswith(".dtsi")):
            continue
        if not fn.startswith(tuple(PLATFORMS)):
            continue

        fp = os.path.join(root, fn)
        if os.path.isfile(fp) or os.path.islink(fp):
            try:
                relpath = os.path.relpath(fp, dirpath).replace(os.sep, "/")
                entry = parse_device_tree_file(fp, relpath)
                if entry:
                    results.append(entry)
            except Exception as e:
                print(f"Error parsing file {fp}: {e}", file=sys.stderr)

    return results


def render_md(entries, outpath):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = []
    lines.append("# MTK Button Summary\n\n")
    lines.append(f"Generated: {now}\n\n")
    lines.append(
        "This document lists mt798* device-tree files that define `gpio-keys` nodes, "
        "with button label, PIO index, and active level.\n\n"
    )

    for platform in PLATFORMS:
        lines.append(f"## {platform.upper()} Platform\n\n")
        filtered = [e for e in entries if e["platform"] == platform]
        if not filtered:
            lines.append("No data.\n\n")
            continue

        lines.append("| Filename | Model | Button Label | PIO | Level |\n")
        lines.append("|---|---|---|---|---|\n")
        for e in filtered:
            fname = f'`{e["path"]}`'
            model = e["model"] or "-"
            first = True
            for btn in e["buttons"]:
                if first:
                    lines.append(
                        f"| {fname} | {model} | {btn['label']} | {btn['pio']} | {btn['level']} |\n"
                    )
                    first = False
                    fname = ""
                    model = ""
                else:
                    lines.append(
                        f"|  |  | {btn['label']} | {btn['pio']} | {btn['level']} |\n"
                    )
        lines.append("\n")

    with open(outpath, "w", encoding="utf-8") as f:
        f.writelines(lines)

    return outpath


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_dts_dir = os.path.join(
        script_dir, "..", "uboot-mtk-20250711", "arch", "arm", "dts"
    )
    default_output_dir = os.path.join(script_dir, "..", "document")

    dts_dir = default_dts_dir
    outname = DEFAULT_OUTPUT_NAME
    recursive = False

    if len(sys.argv) >= 2:
        dts_dir = sys.argv[1]
    if len(sys.argv) >= 3:
        outname = sys.argv[2]
    if len(sys.argv) >= 4:
        recursive = sys.argv[3] in ("--recursive", "-r", "--include-subdirs")

    entries = collect(dts_dir, recursive=recursive)
    outpath = os.path.join(default_output_dir, outname)
    render_md(entries, outpath)
    print(f"Exported to: {outpath}, processed {len(entries)} device-tree files.")


if __name__ == "__main__":
    main()
