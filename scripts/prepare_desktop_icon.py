from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


def prepare(source: Path, destination: Path, size: int) -> None:
    if size <= 0:
        raise ValueError("Icon size must be positive")
    with Image.open(source) as image:
        converted = image.convert("RGBA")
        resized = converted.resize((size, size), Image.Resampling.LANCZOS)
        destination.parent.mkdir(parents=True, exist_ok=True)
        resized.save(destination, format="PNG")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--size", type=int, default=512)
    args = parser.parse_args()
    prepare(args.source, args.destination, args.size)


if __name__ == "__main__":
    main()
