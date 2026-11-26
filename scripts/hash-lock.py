#!/usr/bin/env python3
"""Add `--hash` lines to backend/requirements.lock.

The image and CI install with `pip install --require-hashes`, so every file pip
may download has to be listed with its SHA-256. This script reads the pins
(`name==version`) from the lock file, asks PyPI for the files of each release
and rewrites the lock with the hashes of the wheels usable on the platforms the
project targets: CPython 3.11 on Linux x86_64 and aarch64 (glibc).

Usage (from the repository root, needs network access to pypi.org):

    python3 scripts/hash-lock.py            # rewrite backend/requirements.lock in place
    python3 scripts/hash-lock.py --check    # exit 1 if a pin has no hash or hashes are stale

Workflow to update dependencies: edit the versions in the lock (or regenerate
the pins with `pip freeze`, see the header of the lock file), run this script,
then rebuild the image and run the tests.

Only the Python standard library is used.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

LOCK = Path(__file__).resolve().parent.parent / "backend" / "requirements.lock"
PYTHON_MINOR = 11
ARCHS = ("x86_64", "aarch64")
PIN_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s\\;]+)")


def wheel_is_usable(filename: str) -> bool:
    """True for wheels pip can install on CPython 3.11 / Linux glibc / x86_64 or aarch64."""
    parts = filename[:-4].split("-")
    if len(parts) < 5:
        return False
    py_tags, abi_tags, plat_tags = parts[-3].split("."), parts[-2].split("."), parts[-1].split(".")

    def py_ok(tag: str, abis: list[str]) -> bool:
        if tag in ("py3", "py2", f"py3{PYTHON_MINOR}", f"cp3{PYTHON_MINOR}"):
            return tag != "py2" or "py3" in py_tags
        m = re.fullmatch(r"cp3(\d+)", tag)
        return bool(m) and int(m.group(1)) <= PYTHON_MINOR and "abi3" in abis

    if not any(py_ok(t, abi_tags) for t in py_tags):
        return False
    if not any(a in ("none", "abi3", f"cp3{PYTHON_MINOR}") for a in abi_tags):
        return False

    def plat_ok(tag: str) -> bool:
        if tag == "any":
            return True
        if tag.startswith("musllinux") or not (tag.startswith("manylinux") or tag.startswith("linux")):
            return False
        return tag.endswith(ARCHS)

    return any(plat_ok(t) for t in plat_tags)


def release_hashes(name: str, version: str) -> tuple[list[str], list[str]]:
    """Return (hashes, notes) for one pinned release."""
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    req = urllib.request.Request(url, headers={"User-Agent": "predomicsapp-hash-lock"})
    last_error: Exception | None = None
    for _ in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                files = json.load(resp)["urls"]
            break
        except Exception as exc:  # network hiccup: retry
            last_error = exc
    else:
        raise SystemExit(f"Could not query PyPI for {name}=={version}: {last_error}")

    notes: list[str] = []
    wheels = [f for f in files if f["packagetype"] == "bdist_wheel" and wheel_is_usable(f["filename"])]
    chosen = wheels
    if not wheels:
        chosen = [f for f in files if f["packagetype"] == "sdist"]
        notes.append("no compatible wheel: pip will build from the source archive")
    else:
        covered = {arch for f in wheels for arch in ARCHS
                   if f["filename"].endswith("any.whl") or arch in f["filename"]}
        missing = [a for a in ARCHS if a not in covered]
        if missing:
            notes.append(f"no wheel for {', '.join(missing)}")
    if not chosen:
        raise SystemExit(f"{name}=={version}: PyPI lists no usable file")
    return sorted({f["digests"]["sha256"] for f in chosen}), notes


def parse_lock(text: str) -> tuple[list[str], list[tuple[str, str]], dict[tuple[str, str], list[str]]]:
    """Split the lock into (header comment lines, pins in order, existing hashes per pin)."""
    header: list[str] = []
    pins: list[tuple[str, str]] = []
    existing: dict[tuple[str, str], list[str]] = {}
    current: tuple[str, str] | None = None
    for line in text.splitlines():
        stripped = line.strip()
        m = PIN_RE.match(stripped)
        if m:
            current = (m.group(1), m.group(2))
            pins.append(current)
            existing[current] = re.findall(r"--hash=sha256:([0-9a-f]{64})", stripped)
        elif stripped.startswith("--hash=") and current:
            existing[current] += re.findall(r"--hash=sha256:([0-9a-f]{64})", stripped)
        elif stripped.startswith("#") and not pins:
            header.append(line)
    return header, pins, existing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="verify instead of rewriting")
    parser.add_argument("--lock", type=Path, default=LOCK)
    args = parser.parse_args()

    header, pins, existing = parse_lock(args.lock.read_text())
    if not pins:
        raise SystemExit(f"No pinned requirements found in {args.lock}")

    out = header + [""] if header else []
    problems = 0
    for name, version in pins:
        hashes, notes = release_hashes(name, version)
        for note in notes:
            print(f"note: {name}=={version}: {note}", file=sys.stderr)
        if args.check and sorted(set(existing[(name, version)])) != hashes:
            print(f"stale or missing hashes: {name}=={version}", file=sys.stderr)
            problems += 1
        out.append(f"{name}=={version} \\")
        out += [f"    --hash=sha256:{h}" + (" \\" if i < len(hashes) - 1 else "") for i, h in enumerate(hashes)]

    if args.check:
        print(f"{len(pins)} pins checked, {problems} problem(s)")
        return 1 if problems else 0
    args.lock.write_text("\n".join(out) + "\n")
    print(f"Wrote {args.lock} ({len(pins)} pins)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
