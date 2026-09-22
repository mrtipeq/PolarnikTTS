#!/usr/bin/env python3
"""Build Chrome Web Store packages of the extension.

    python scripts/pack_extension.py [--key PATH_TO_key.pem]

Outputs in dist/:
  PolarnikTTS-<version>-store.zip           manifest without "key" (the store rejects it)
  PolarnikTTS-<version>-store-with-key.zip  same + key.pem in the zip root: use this for the FIRST
                                             upload so the store keeps the extension id
                                             gocceeipamkkjphdecegbhbghhogeidb (native messaging host)
  PolarnikTTS-<version>-unpacked.zip        the folder as is, for "Load unpacked" users
"""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / "extension"
DIST = ROOT / "dist"
SKIP = {".DS_Store", "Thumbs.db"}


def add_dir(zf: zipfile.ZipFile, base: Path, prefix: str = "", manifest_override: bytes | None = None) -> None:
    for p in sorted(base.rglob("*")):
        if p.is_dir() or p.name in SKIP:
            continue
        rel = p.relative_to(base).as_posix()
        if rel == "manifest.json" and manifest_override is not None:
            zf.writestr(prefix + rel, manifest_override)
        else:
            zf.write(p, prefix + rel)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--key", help="private key (.pem) matching the 'key' in manifest.json")
    args = ap.parse_args()

    manifest = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
    version = manifest["version"]
    store_manifest = {k: v for k, v in manifest.items() if k != "key"}
    store_bytes = (json.dumps(store_manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    DIST.mkdir(exist_ok=True)

    out_unpacked = DIST / f"PolarnikTTS-{version}-unpacked.zip"
    with zipfile.ZipFile(out_unpacked, "w", zipfile.ZIP_DEFLATED) as zf:
        add_dir(zf, EXT, "PolarnikTTS-extension/")
    print("wrote", out_unpacked)

    out_store = DIST / f"PolarnikTTS-{version}-store.zip"
    with zipfile.ZipFile(out_store, "w", zipfile.ZIP_DEFLATED) as zf:
        add_dir(zf, EXT, "", store_bytes)
    print("wrote", out_store)

    if args.key:
        key = Path(args.key)
        if not key.exists():
            raise SystemExit(f"key not found: {key}")
        out_key = DIST / f"PolarnikTTS-{version}-store-with-key.zip"
        with zipfile.ZipFile(out_key, "w", zipfile.ZIP_DEFLATED) as zf:
            add_dir(zf, EXT, "", store_bytes)
            zf.write(key, "key.pem")
        print("wrote", out_key, "(first store upload only)")


if __name__ == "__main__":
    main()
