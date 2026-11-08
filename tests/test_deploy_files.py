"""The Cloud Build upload for the API must contain what the image needs.

gcloud reads .gcloudignore with gitignore rules. A wrong pattern once
dropped api/ from the upload and the build failed, so check it here.
"""
from pathlib import Path

import pathspec
import pytest

from api.main import PRODUCTION_VERSION

ROOT = Path(__file__).resolve().parent.parent
MODEL_DIR = ROOT / "ml" / "models" / PRODUCTION_VERSION


def required_paths() -> list[str]:
    paths = ["Dockerfile", "api/__init__.py", "api/main.py", "api/predictor.py", "api/schemas.py",
             "api/requirements.txt", "ml/__init__.py", "ml/features.py", "ml/explain.py"]
    paths += [p.relative_to(ROOT).as_posix() for p in MODEL_DIR.rglob("*") if p.is_file()]
    return paths


def ignored(ignore_text: str, paths: list[str]) -> list[str]:
    spec = pathspec.GitIgnoreSpec.from_lines(ignore_text.splitlines())
    return [p for p in paths if spec.match_file(p)]


def test_served_model_folder_has_the_files_the_api_loads():
    names = {p.name for p in MODEL_DIR.iterdir()}
    assert {"model.joblib", "location_lookup.json", "metrics.json"} <= names


def test_gcloudignore_does_not_exclude_what_the_api_image_needs():
    text = (ROOT / ".gcloudignore").read_text(encoding="utf8")
    assert ignored(text, required_paths()) == []


@pytest.mark.parametrize("bad", ["api/", "ml/features.py", "ml/explain.py", "*.joblib",
                                 f"ml/models/{PRODUCTION_VERSION}/", "ml/models/"])
def test_the_check_itself_catches_a_bad_pattern(bad):
    assert ignored(f"android_app/\n{bad}\n", required_paths()) != []
