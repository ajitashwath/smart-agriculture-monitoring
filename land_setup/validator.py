from __future__ import annotations

import json
from pathlib import Path
from typing import Union

from pydantic import ValidationError

from land_setup.schemas import FarmProfile

PROFILES_DIR = Path(__file__).parent / "profiles"


class ProfileValidationError(Exception):
    def __init__(self, path: Path, errors: list[dict]) -> None:
        self.path = path
        self.errors = errors
        msgs = "\n".join(
            f"  [{'.'.join(str(l) for l in e['loc'])}] {e['msg']}"
            for e in errors
        )
        super().__init__(f"Validation failed for '{path.name}':\n{msgs}")


def load_profile(path: Union[str, Path]) -> FarmProfile:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Farm profile not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    try:
        return FarmProfile(**raw)
    except ValidationError as exc:
        raise ProfileValidationError(path, exc.errors()) from exc


def load_all_profiles(profiles_dir: Union[str, Path, None] = None) -> dict[str, FarmProfile]:
    directory = Path(profiles_dir) if profiles_dir else PROFILES_DIR
    profiles: dict[str, FarmProfile] = {}
    errors: list[str] = []

    for json_file in sorted(directory.glob("*.json")):
        try:
            profile = load_profile(json_file)
            profiles[profile.farm_id] = profile
        except (ProfileValidationError, FileNotFoundError, json.JSONDecodeError) as exc:
            errors.append(str(exc))

    if errors:
        combined = "\n\n".join(errors)
        raise RuntimeError(f"Some profiles failed to load:\n{combined}")

    return profiles


def validate_profile_file(path: Union[str, Path]) -> tuple[bool, list[str]]:
    try:
        load_profile(path)
        return True, []
    except ProfileValidationError as exc:
        return False, [str(exc)]
    except Exception as exc:
        return False, [f"Unexpected error: {exc}"]
