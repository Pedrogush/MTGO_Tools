#!/usr/bin/env python3
"""Download and extract MTGOSDK NuGet packages into vendor/mtgosdk."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import zipfile
from pathlib import Path

import requests

try:
    from defusedxml.ElementTree import parse as safe_et_parse
except ImportError as exc:  # pragma: no cover
    safe_et_parse = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


ROOT = Path(__file__).resolve().parents[1]
VENDOR_ROOT = ROOT / "vendor" / "mtgosdk"

PACKAGES = ["MTGOSDK", "MTGOSDK.Win32"]


def fetch_latest_version(package: str) -> str:
    index_url = f"https://api.nuget.org/v3-flatcontainer/{package.lower()}/index.json"
    resp = requests.get(index_url, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    versions = data.get("versions")
    if not versions:
        raise RuntimeError(f"No versions found for {package}")
    return versions[-1]


def download_package(package: str, version: str, target: Path) -> Path:
    target.mkdir(parents=True, exist_ok=True)
    filename = target / f"{package}.{version}.nupkg"
    download_url = f"https://api.nuget.org/v3-flatcontainer/{package.lower()}/{version}/{package.lower()}.{version}.nupkg"
    resp = requests.get(download_url, timeout=30)
    resp.raise_for_status()
    filename.write_bytes(resp.content)
    return filename


def extract_package(nupkg: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(nupkg) as zf:
        zf.extractall(destination)


def copy_license_files(source_root: Path) -> None:
    """Put both of MTGOSDK's LICENSE and NOTICE in the vendor root.

    Both, not whichever the package happens to carry first. Apache-2.0 asks a
    redistribution for the License text (4a) and for the NOTICE (4d), and
    packaging/installer.iss ships each of the two it finds. This used to
    ``return`` from inside the loop on the first hit, and the NuGet package root
    carries only NOTICE -- so LICENSE was never copied, the download below was
    never reached, and the installer's entry for it could never fire.
    """
    missing = []
    for name in ("LICENSE", "NOTICE"):
        src = source_root / name
        if src.exists():
            shutil.copy(src, VENDOR_ROOT / name)
        else:
            missing.append(name)
    # Whatever the package left out, from upstream.
    for name in missing:
        response = requests.get(
            f"https://raw.githubusercontent.com/videre-project/MTGOSDK/main/{name}",
            timeout=30,
        )
        response.raise_for_status()
        (VENDOR_ROOT / name).write_bytes(response.content)


def update_sources_json(version: str, commit: str | None) -> None:
    sources_path = ROOT / "vendor" / "vendor_sources.json"
    if sources_path.exists():
        data = json.loads(sources_path.read_text(encoding="utf-8"))
    else:
        data = {}
    for package in PACKAGES:
        entry = data.setdefault(package, {})
        entry["repository"] = "https://github.com/videre-project/MTGOSDK"
        entry["version"] = version
        if commit:
            entry["commit"] = commit
    sources_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def resolve_commit(nuspec_path: Path) -> str | None:
    if safe_et_parse is None:
        return None
    root = safe_et_parse(nuspec_path).getroot()
    namespace = {"ns": root.tag.split("}")[0].strip("{")}
    repo = root.find("ns:metadata/ns:repository", namespace)
    if repo is None:
        return None
    return repo.attrib.get("commit")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", help="Specific MTGOSDK version (defaults to latest)")
    args = parser.parse_args()

    if safe_et_parse is None:
        print(
            "defusedxml not installed; skipping MTGOSDK vendor refresh. "
            "Install via `pip install defusedxml` to enable.",
            file=sys.stderr,
        )
        if _IMPORT_ERROR is not None:
            print(f"Import error: {_IMPORT_ERROR}", file=sys.stderr)
        return 0

    version = args.version or fetch_latest_version(PACKAGES[0])
    VENDOR_ROOT.mkdir(parents=True, exist_ok=True)

    commit_hash: str | None = None
    for package in PACKAGES:
        print(f"Fetching {package} {version}…")
        nupkg = download_package(package, version, VENDOR_ROOT)
        extract_dir = VENDOR_ROOT / package
        extract_package(nupkg, extract_dir)
        nuspec = next(extract_dir.glob("*.nuspec"), None)
        if nuspec is not None and commit_hash is None:
            commit_hash = resolve_commit(nuspec)

    copy_license_files(VENDOR_ROOT / PACKAGES[0])
    update_sources_json(version, commit_hash)
    print("MTGOSDK vendor refresh complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
