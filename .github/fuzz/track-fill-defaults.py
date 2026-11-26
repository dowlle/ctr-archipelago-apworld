"""Pin unrelated options to the tested apworld's defaults for the fill arm."""

from pathlib import Path
import sys

import yaml

from worlds.AutoWorld import AutoWorldRegister
from worlds.ctr import track_fill


game = "Crash Team Racing"
path = Path(sys.argv[1])
overrides = yaml.safe_load(path.read_text(encoding="utf-8"))[game]
expected = {"acid-lake": ("time_crates", 29), "arabian-heights-day": ("weapon_crates", 27)}
for descriptor in overrides["custom_tracks"]:
    lev_sha = next(file["sha256"] for file in descriptor["files"] if file["role"] == "lev")
    fill = track_fill.bundled(descriptor["content_id"], lev_sha, descriptor["laps"])
    family, count = expected[descriptor["content_id"]]
    if not fill or fill["counts"][family] != count:
        raise SystemExit(f"The packed {descriptor['display_name']} fixture must carry all {count} {family}.")

options = AutoWorldRegister.world_types[game].options_dataclass.type_hints
defaults = {}
for name, option in options.items():
    value = option.default
    if isinstance(value, frozenset):
        value = sorted(value)
    elif isinstance(value, tuple):
        value = list(value)
    defaults[name] = value

path.write_text(yaml.safe_dump({game: defaults | overrides}), encoding="utf-8")
