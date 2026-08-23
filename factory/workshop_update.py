#!/usr/bin/env python3
"""Preview or apply a drift-safe update of workshop-owned files."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
from pathlib import Path


SCHEMA_VERSION = 1
MANIFEST = Path(".factory/workshop-install.json")
MANAGED_DIRECTORIES = (Path("factory"), Path("workshop-guide"))
MANAGED_ROOT_FILES = (Path("setup_demo.sh"), Path("recipe-app-prd.md"), Path("vercel.json"))
IGNORED_PARTS = {
    ".factory", ".git", ".next", ".pytest_cache", ".wrangler", "__pycache__",
    "dist", "node_modules",
}
VERSION_PATTERN = re.compile(r'WORKSHOP_VERSION\s*=\s*["\']([^"\']+)["\']')


class UpdateError(ValueError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def workshop_version(repo: Path) -> str:
    path = repo / "factory/factory_contracts.py"
    if not path.is_file():
        raise UpdateError(f"Workshop version file is missing: {path}")
    match = VERSION_PATTERN.search(path.read_text())
    if not match:
        raise UpdateError(f"WORKSHOP_VERSION is missing from {path}")
    return match.group(1)


def _managed_candidates(repo: Path):
    for directory in MANAGED_DIRECTORIES:
        root = repo / directory
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(repo)
            if any(part in IGNORED_PARTS for part in relative.parts):
                continue
            if path.is_symlink():
                raise UpdateError(f"Managed workshop path must not be a symlink: {relative}")
            if path.is_file():
                yield relative, path
    for relative in MANAGED_ROOT_FILES:
        path = repo / relative
        if path.is_symlink():
            raise UpdateError(f"Managed workshop path must not be a symlink: {relative}")
        if path.is_file():
            yield relative, path


def inventory(repo: Path) -> dict[str, dict]:
    return {
        relative.as_posix(): {
            "sha256": sha256(path),
            "mode": stat.S_IMODE(path.stat().st_mode),
        }
        for relative, path in _managed_candidates(repo)
    }


def load_manifest(target: Path) -> dict:
    path = target / MANIFEST
    if not path.is_file():
        raise UpdateError(
            "No workshop install manifest was found. Use the installed version's "
            "`factory/update_workshop.sh --record-current` first, or create a fresh "
            "checkout with `factory/new_workshop.sh`."
        )
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise UpdateError(f"Workshop install manifest is invalid: {exc}") from exc
    if value.get("schema_version") != SCHEMA_VERSION or not isinstance(value.get("files"), dict):
        raise UpdateError("Workshop install manifest has an unsupported schema; use a fresh checkout.")
    return value


def write_manifest(target: Path, version: str, files: dict[str, dict]) -> Path:
    path = target / MANIFEST
    path.parent.mkdir(parents=True, exist_ok=True)
    value = {"schema_version": SCHEMA_VERSION, "version": version, "files": files}
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)
    return path


def current_entry(target: Path, relative: str) -> dict | None:
    path = target / relative
    if path.is_symlink():
        raise UpdateError(f"Managed workshop path must not be a symlink: {relative}")
    if not path.is_file():
        return None
    return {"sha256": sha256(path), "mode": stat.S_IMODE(path.stat().st_mode)}


def normalized_entry(value) -> dict:
    if isinstance(value, str):
        return {"sha256": value, "mode": None}
    return value if isinstance(value, dict) else {}


def plan_update(source: Path, target: Path, installed: dict) -> tuple[list[tuple[str, str]], list[str], dict]:
    source_files = inventory(source)
    previous = installed["files"]
    drift = []
    for relative, raw_entry in sorted(previous.items()):
        expected = normalized_entry(raw_entry).get("sha256")
        actual = current_entry(target, relative)
        if actual is None or actual.get("sha256") != expected:
            drift.append(relative)
    for relative, source_entry in sorted(source_files.items()):
        if relative in previous:
            continue
        actual = current_entry(target, relative)
        if actual is not None and actual["sha256"] != source_entry["sha256"]:
            drift.append(relative)

    operations = []
    for relative, source_entry in sorted(source_files.items()):
        previous_entry = normalized_entry(previous.get(relative))
        if not previous_entry:
            operations.append(("ADD", relative))
        elif previous_entry.get("sha256") != source_entry["sha256"] or previous_entry.get("mode") != source_entry["mode"]:
            operations.append(("UPDATE", relative))
    for relative in sorted(set(previous) - set(source_files)):
        operations.append(("REMOVE", relative))
    return operations, sorted(set(drift)), source_files


def apply_update(source: Path, target: Path, operations: list[tuple[str, str]], source_files: dict[str, dict]):
    for action, relative in operations:
        destination = target / relative
        if action == "REMOVE":
            destination.unlink()
            continue
        origin = source / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origin, destination, follow_symlinks=False)
        os.chmod(destination, source_files[relative]["mode"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Preview or apply a versioned update to workshop-owned files without overwriting local drift.",
    )
    parser.add_argument("--target", type=Path, default=Path.cwd(), help="attendee repository to inspect")
    parser.add_argument("--source", type=Path, help="clean checkout of the workshop release to install")
    parser.add_argument("--record-current", action="store_true", help="record the installed version without changing files")
    parser.add_argument("--apply", action="store_true", help="apply the displayed clean update")
    args = parser.parse_args(argv)
    target = args.target.resolve()
    try:
        if args.record_current:
            if args.source or args.apply:
                raise UpdateError("--record-current cannot be combined with --source or --apply")
            files = inventory(target)
            path = write_manifest(target, workshop_version(target), files)
            print(f"Recorded {len(files)} workshop-managed files at {path}")
            return 0
        if not args.source:
            raise UpdateError("--source is required unless --record-current is used")
        source = args.source.resolve()
        installed = load_manifest(target)
        operations, drift, source_files = plan_update(source, target, installed)
        if drift:
            for relative in drift:
                print(f"DRIFT {relative}", file=sys.stderr)
            raise UpdateError(
                "Resolve drift or preserve the customized files manually; no file was overwritten."
            )
        print(f"Installed: {installed.get('version', 'unknown')}")
        print(f"Available: {workshop_version(source)}")
        if operations:
            for action, relative in operations:
                print(f"{action} {relative}")
        else:
            print("No workshop-managed file changes.")
        if not args.apply:
            print("Preview only. Re-run with --apply after reviewing this list.")
            return 0
        apply_update(source, target, operations, source_files)
        path = write_manifest(target, workshop_version(source), source_files)
        print(f"Applied {len(operations)} change(s). Updated manifest: {path}")
        return 0
    except (OSError, UpdateError) as exc:
        print(f"factory update: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
