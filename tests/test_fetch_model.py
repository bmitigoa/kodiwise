import json

import pytest

from data_pipeline.job import LocalStore
from ml.fetch_model import MANIFEST_NAME, SNAPSHOT_NAME, fetch_version, upload_version

V = "v20261201-appX"


def _make(tmp_path):
    models, snaps = tmp_path / "models", tmp_path / "snaps"
    (models / V).mkdir(parents=True)
    snaps.mkdir()
    (models / V / "model.joblib").write_bytes(b"model-bytes")
    (models / V / "metrics.json").write_text('{"a": 1}')
    (snaps / f"{V}.csv").write_text("x,y\n1,2\n")
    return models, snaps


def test_upload_then_restore_into_an_empty_clone(tmp_path):
    models, snaps = _make(tmp_path)
    store = LocalStore(tmp_path / "bucket")
    res = upload_version(store, V, models, snaps)
    assert sorted(res["uploaded"]) == sorted(["model.joblib", "metrics.json", SNAPSHOT_NAME])
    assert f"models/{V}/{MANIFEST_NAME}" in store.list("models/")

    fresh_models, fresh_snaps = tmp_path / "m2", tmp_path / "s2"
    out = fetch_version(store, V, fresh_models, fresh_snaps)
    assert (fresh_models / V / "model.joblib").read_bytes() == b"model-bytes"
    assert (fresh_snaps / f"{V}.csv").read_text() == "x,y\n1,2\n"
    assert SNAPSHOT_NAME in out["written"]
    # a second restore changes nothing
    assert fetch_version(store, V, fresh_models, fresh_snaps)["written"] == []


def test_upload_is_repeatable_but_never_overwrites(tmp_path):
    models, snaps = _make(tmp_path)
    store = LocalStore(tmp_path / "bucket")
    upload_version(store, V, models, snaps)
    again = upload_version(store, V, models, snaps)
    assert again["uploaded"] == [] and len(again["already_there"]) == 3
    (models / V / "model.joblib").write_bytes(b"changed")
    with pytest.raises(FileExistsError):
        upload_version(store, V, models, snaps)
    assert store.read(f"models/{V}/model.joblib") == b"model-bytes"


def test_restore_detects_corruption_and_will_not_overwrite_local_files(tmp_path):
    models, snaps = _make(tmp_path)
    store = LocalStore(tmp_path / "bucket")
    upload_version(store, V, models, snaps)
    # a corrupted object
    (tmp_path / "bucket" / "models" / V / "model.joblib").write_bytes(b"corrupt")
    with pytest.raises(ValueError):
        fetch_version(store, V, tmp_path / "m2", tmp_path / "s2")
    # a differing local file is kept unless forced
    (tmp_path / "bucket" / "models" / V / "model.joblib").write_bytes(b"model-bytes")
    other = tmp_path / "m3"
    (other / V).mkdir(parents=True)
    (other / V / "model.joblib").write_bytes(b"different")
    with pytest.raises(FileExistsError):
        fetch_version(store, V, other, tmp_path / "s3")
    fetch_version(store, V, other, tmp_path / "s3", force=True)
    assert (other / V / "model.joblib").read_bytes() == b"model-bytes"


def test_missing_backup_and_bad_names(tmp_path):
    store = LocalStore(tmp_path / "bucket")
    with pytest.raises(FileNotFoundError):
        fetch_version(store, V, tmp_path / "m", tmp_path / "s")
    with pytest.raises(ValueError):
        fetch_version(store, "../evil", tmp_path / "m", tmp_path / "s")
    with pytest.raises(FileNotFoundError):
        upload_version(store, V, tmp_path / "none", tmp_path / "s")
