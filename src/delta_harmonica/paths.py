from __future__ import annotations

from pathlib import Path


def project_root() -> Path:
    """Repo root when editable-installed from source; else cwd."""
    here = Path(__file__).resolve()
    # src/delta_harmonica/paths.py -> repo root
    candidate = here.parents[2]
    if (candidate / "scores").is_dir() or (candidate / "pyproject.toml").is_file():
        return candidate
    return Path.cwd()


def scores_dir() -> Path:
    return project_root() / "scores"


def profiles_dir() -> Path:
    return project_root() / "profiles"


def resolve_score_path(name_or_path: str) -> Path:
    path = Path(name_or_path)
    if path.is_file():
        return path.resolve()

    base = scores_dir()
    candidates = [
        base / name_or_path,
        base / f"{name_or_path}.txt",
    ]
    for c in candidates:
        if c.is_file():
            return c.resolve()
    raise FileNotFoundError(
        f"score not found: {name_or_path!r} (looked in {base})"
    )


def resolve_profile_path(name: str) -> Path:
    path = Path(name)
    if path.suffix == ".json" and path.is_file():
        return path.resolve()
    p = profiles_dir() / f"{name}.json"
    if p.is_file():
        return p.resolve()
    raise FileNotFoundError(
        f"profile not found: {name!r} (expected {profiles_dir() / (name + '.json')})"
    )
