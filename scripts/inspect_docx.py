#!/usr/bin/env python3
"""
Inspect DOCX ingestion results without printing raw text.
"""

import argparse
import json
import sys
from pathlib import Path

from backend_lite.ingest.docx import DOCXParser


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect DOCX ingestion output.")
    parser.add_argument("path", help="Path to DOCX file")
    parser.add_argument("--limit", type=int, default=5, help="Max blocks to show")
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        print(json.dumps({"error": "file_not_found", "path": str(path)}))
        return 1

    data = path.read_bytes()
    result = DOCXParser().parse(data, filename=path.name)

    blocks = result.all_blocks
    preview = []
    for block in blocks[: max(args.limit, 0)]:
        preview.append({
            "block_index": block.block_index,
            "page_no": block.page_no,
            "paragraph_index": block.paragraph_index,
            "char_start": block.char_start,
            "char_end": block.char_end,
            "length": (block.char_end - block.char_start) if block.char_end is not None and block.char_start is not None else None,
        })

    output = {
        "page_count": result.page_count,
        "block_count": len(blocks),
        "metadata": result.metadata,
        "block_preview": preview,
    }
    print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
