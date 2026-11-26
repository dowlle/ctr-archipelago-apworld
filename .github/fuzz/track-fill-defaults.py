"""Pin unrelated options to the tested apworld's defaults for the fill arm."""

from pathlib import Path
import sys

import yaml

from worlds.AutoWorld import AutoWorldRegister


game = "Crash Team Racing"
path = Path(sys.argv[1])
overrides = yaml.safe_load(path.read_text(encoding="utf-8"))[game]
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
