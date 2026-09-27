from __future__ import annotations

import json
from pathlib import Path

from delta_harmonica.models import Profile, UI_KEYS
from delta_harmonica.paths import profiles_dir


def load_profile(path: Path) -> Profile:
    data = json.loads(path.read_text(encoding="utf-8"))
    profile = Profile.from_dict(data)
    missing = [k for k in UI_KEYS if k not in profile.keys]
    if missing:
        raise ValueError(
            f"profile incomplete, missing keys: {', '.join(missing)}"
        )
    return profile


def save_profile(profile: Profile, path: Path | None = None) -> Path:
    profiles_dir().mkdir(parents=True, exist_ok=True)
    out = path or (profiles_dir() / f"{profile.name}.json")
    out.write_text(
        json.dumps(profile.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return out
