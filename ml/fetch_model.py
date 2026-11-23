"""Back up and restore model versions in the private scrape bucket.

    python -m ml.fetch_model                      # restore the version api/main.py serves
    python -m ml.fetch_model v20261123-appF       # restore a named version
    python -m ml.fetch_model --upload v20261123-appF   # back a version up by hand

Bucket layout (gs://rent-prediction-ar-kodiwise-scrape/models/<version>/):
  every file of ml/models/<version>/ (model.joblib, metrics.json, ...), plus
  snapshot.csv   = data/processed/snapshots/<version>.csv, the exact rows the version
                   was trained on (the deploy rule needs it to compare a later candidate),
  MANIFEST.json  = sha256 of each file, written last and checked on restore.

Versions are immutable: an upload never overwrites an object, and a restore never
replaces a local file with different content (use --force to do that on purpose).
`python -m ml.retrain` uploads each new version automatically.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "ml" / "models"
SNAPSHOT_DIR = ROOT / "data" / "processed" / "snapshots"
DEFAULT_BUCKET = "rent-prediction-ar-kodiwise-scrape"
PREFIX = "models"
SNAPSHOT_NAME = "snapshot.csv"
MANIFEST_NAME = "MANIFEST.json"
VERSION_RE = re.compile(r"^v\d{8}(-[A-Za-z0-9]+)?$")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _check_version(version: str) -> str:
    if not VERSION_RE.match(version):
        raise ValueError(f"not a model version name: {version!r}")
    return version


def local_files(version: str, models_dir: Path = MODELS_DIR, snapshot_dir: Path = SNAPSHOT_DIR) -> dict[str, Path]:
    """Object name (under models/<version>/) -> local file."""
    folder = models_dir / _check_version(version)
    if not (folder / "model.joblib").exists():
        raise FileNotFoundError(f"{folder / 'model.joblib'} not found")
    files = {p.name: p for p in sorted(folder.iterdir()) if p.is_file()}
    snap = snapshot_dir / f"{version}.csv"
    if snap.exists():
        files[SNAPSHOT_NAME] = snap
    return files


def upload_version(store, version: str, models_dir: Path = MODELS_DIR, snapshot_dir: Path = SNAPSHOT_DIR) -> dict:
    """Copy a version to models/<version>/. Never overwrites: an object that is already there must
    be identical, otherwise this raises (a version is immutable)."""
    files = local_files(version, models_dir, snapshot_dir)
    manifest: dict[str, str] = {}
    uploaded, already = [], []
    for name, path in files.items():
        data = path.read_bytes()
        manifest[name] = _sha(data)
        obj = f"{PREFIX}/{version}/{name}"
        try:
            store.write_new(obj, data)
            uploaded.append(name)
        except FileExistsError:
            if _sha(store.read(obj)) != manifest[name]:
                raise FileExistsError(f"{obj} already exists with different content; versions are immutable") from None
            already.append(name)
    body = json.dumps({"version": version, "files": manifest}, indent=2, sort_keys=True).encode()
    try:
        store.write_new(f"{PREFIX}/{version}/{MANIFEST_NAME}", body)
    except FileExistsError:
        old = json.loads(store.read(f"{PREFIX}/{version}/{MANIFEST_NAME}"))
        if old.get("files") != manifest:
            raise FileExistsError(f"{PREFIX}/{version}/{MANIFEST_NAME} differs from the local files") from None
    return {"version": version, "uploaded": uploaded, "already_there": already, "files": len(files)}


def fetch_version(store, version: str, models_dir: Path = MODELS_DIR, snapshot_dir: Path = SNAPSHOT_DIR,
                  force: bool = False) -> dict:
    """Restore models/<version>/ into ml/models/<version>/ (snapshot.csv into data/processed/snapshots/),
    checking every file against MANIFEST.json."""
    _check_version(version)
    try:
        manifest = json.loads(store.read(f"{PREFIX}/{version}/{MANIFEST_NAME}"))["files"]
    except Exception as exc:
        raise FileNotFoundError(f"no complete backup of {version} in the bucket ({type(exc).__name__})") from exc
    written, kept = [], []
    for name, want in manifest.items():
        data = store.read(f"{PREFIX}/{version}/{name}")
        if _sha(data) != want:
            raise ValueError(f"{name}: checksum does not match the manifest; not restored")
        dest = (snapshot_dir / f"{version}.csv") if name == SNAPSHOT_NAME else (models_dir / version / name)
        if dest.exists() and not force:
            if _sha(dest.read_bytes()) != want:
                raise FileExistsError(f"{dest} exists with different content; use --force to replace it")
            kept.append(name)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        written.append(name)
    return {"version": version, "written": written, "unchanged": kept}


def _store(bucket: str):
    from data_pipeline.job import GcsStore
    return GcsStore(bucket)


def _served_version() -> str:
    m = re.search(r'^PRODUCTION_VERSION\s*=\s*"([^"]+)"', (ROOT / "api" / "main.py").read_text(encoding="utf-8"), re.M)
    if not m:
        raise RuntimeError("PRODUCTION_VERSION not found in api/main.py")
    return m.group(1)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("version", nargs="?", help="model version (default: the one api/main.py serves)")
    ap.add_argument("--upload", action="store_true", help="back the version up instead of restoring it")
    ap.add_argument("--bucket", default=DEFAULT_BUCKET)
    ap.add_argument("--force", action="store_true", help="replace local files that differ")
    args = ap.parse_args(argv)
    try:
        version = args.version or _served_version()
        store = _store(args.bucket)
        result = (upload_version(store, version) if args.upload
                  else fetch_version(store, version, force=args.force))
    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        print(f"error: {exc}")
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
