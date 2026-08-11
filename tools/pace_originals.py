#!/usr/bin/env python3
"""Copy-desk helper: split over-long paragraphs in originals at sentence
boundaries, using the exact rule the renderer already applies.

The reader already sees these paragraphs split — `longform._flow` reflows any
plain-prose paragraph past 70 words into ~55-word chunks on every surface. This
script writes that same split back into the source file, so the copy on disk
matches the copy on the page and `build.py` stops flagging the file.

Usage:  python3 tools/pace_originals.py originals/<file>.txt [...]

Only plain prose is touched. Headings, bullets, numbered lists, pull quotes,
tables, images and video directives are left exactly as they are, matching the
skip list in build.py's pacing watch.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from longform import MAX_PARA_WORDS, _flow  # noqa: E402

SKIP_PREFIXES = ("#", "-", "*", ">", "|", "!", "1", "2", "3", "4", "5", "6",
                 "7", "8", "9")


def repace(body):
    """Return the body with over-long prose paragraphs split; count the splits."""
    blocks = re.split(r"\n\s*\n", body)
    out, split_count = [], 0
    for block in blocks:
        stripped = block.lstrip()
        if stripped.startswith(SKIP_PREFIXES) or len(block.split()) <= MAX_PARA_WORDS:
            out.append(block)
            continue
        chunks = _flow(" ".join(block.split("\n")))
        if len(chunks) > 1:
            split_count += 1
        out.append("\n\n".join(chunks))
    return "\n\n".join(out), split_count


def main(paths):
    total = 0
    for name in paths:
        path = Path(name)
        text = path.read_text(encoding="utf-8")
        head, sep, body = text.partition("\n---\n")
        if not sep:
            print(f"  skipped {path.name}: no header separator")
            continue
        new_body, count = repace(body)
        if not count:
            print(f"  unchanged {path.name}")
            continue
        path.write_text(head + sep + new_body, encoding="utf-8")
        total += count
        print(f"  paced {path.name}: {count} paragraph(s) split")
    print(f"{total} paragraph(s) split across {len(paths)} file(s)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])
