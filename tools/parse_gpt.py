#!/usr/bin/env python3
# Copyright (c) 2026 Yuzhii0718
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
"""Parse the TXT output of 'mtk_gpt.py --show' and emit a JSON partition layout.

Usage:
    python3 parse_gpt.py --i <gptinfo.txt> --o <output.json>

The generated JSON contains only the partitions described in the TXT dump
(no extra or synthesized entries).
"""

import argparse
import json
import re


def parse_gpt_info(filepath):
    """Parse mtk_gpt.py --show TXT output into a list of partition dicts.

    Returns:
        list of dict: each dict has 'name', 'start', 'end', 'unique_part_guid'
    """
    partitions = []

    with open(filepath, 'r') as f:
        lines = f.readlines()

    current = {}
    for line in lines:
        line_stripped = line.strip()

        # New partition header: "[PARTITION] Name: xxxx"
        m = re.match(r'^\[PARTITION\]\s+Name:\s*(.*)', line_stripped)
        if m:
            if current.get('start') is not None and current.get('end') is not None:
                partitions.append(current)
            current = {'name': m.group(1).strip()}
            continue

        # unique guid
        m = re.match(r'^\s*unique guid:\s*(\{[0-9a-fA-F\-]+\})', line_stripped)
        if m:
            current['unique_part_guid'] = m.group(1)
            continue

        # start blk
        m = re.match(r'^\s*start blk:\s*(\d+)', line_stripped)
        if m:
            current['start'] = int(m.group(1))
            continue

        # last blk  (treated as "end")
        m = re.match(r'^\s*last blk:\s*(\d+)', line_stripped)
        if m:
            current['end'] = int(m.group(1))
            continue

    # Save the final partition
    if current.get('start') is not None and current.get('end') is not None:
        partitions.append(current)

    return partitions


def generate_json(partitions):
    """Build a JSON-serialisable dict from the raw partition list.

    Only *named* partitions are emitted.  Unnamed / free-space entries are
    silently dropped.  No extra synthetic entries (e.g. a "gpt" header range)
    are added – the output is faithful to the TXT input.
    """
    result = {}
    for p in partitions:
        name = p.get('name')
        if not name:
            continue

        entry = {
            "start": p['start'],
            "end": p['end'],
        }
        if p.get('unique_part_guid'):
            entry["unique_part_guid"] = p['unique_part_guid']

        result[name] = entry

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Convert 'mtk_gpt.py --show' TXT dump to JSON partition layout"
    )
    parser.add_argument(
        "--i", nargs=1, required=True,
        help="input file (TXT output of 'mtk_gpt.py --show')",
        dest="input",
    )
    parser.add_argument(
        "--o", nargs=1, required=True,
        help="output JSON file",
        dest="output",
    )
    args = parser.parse_args()

    input_file = args.input[0]
    output_file = args.output[0]

    partitions = parse_gpt_info(input_file)
    data = generate_json(partitions)

    with open(output_file, 'w') as f:
        json.dump(data, f, indent='\t', ensure_ascii=False)
        f.write('\n')

    print("GPT JSON written to: %s" % output_file)
    print("  Partitions: %d entries" % len(data))


if __name__ == '__main__':
    main()
