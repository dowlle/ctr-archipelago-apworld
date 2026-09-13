"""Lettersanity -- the C, T and R letters as checks and as items (#148).

WHAT THIS CLASS CHECKS AND WHERE THE SIGNAL COMES FROM. Each of the three CTR
letters on each of the 16 tracks that carry a CTR Token Challenge. Physically
grabbing a letter sends its check; in the item-bearing shapes an unreceived
letter renders translucent and cannot be picked up at all, and the CTR Token
Challenge can only be won once the letters that seed selected have arrived.

WHO OWNS THE SEMANTICS. The apworld owns the names, the per-seed subset, the
token-challenge rule and the item pool; native owns the pickup hook and the
translucency. Neither half is built here.

THE FOUR SHAPES (live [#148] body, design-reviewed). `off` mints nothing.
`locations_only` creates the 48 locations. `locations_and_items` creates the 48
locations AND the 48 items. `items_only` creates the 48 items and no locations. A
separate knob picks whether 1, 2 or 3 letters per track count for a seed, chosen
randomly per track at generation, and it applies only to the two location-bearing
shapes. Every shape draws from the SAME frozen 48 location names and the SAME
frozen 48 item names -- which is exactly why one bump covers all four.

DATAPACKAGE STABILITY. This class claims the additive block 35012500, stride 3
per track in TROPHY_TRACKS order (C, T, R within a track), and registers all 48
names UNCONDITIONALLY. 35012500 was reserved for lettersanity by the #145
itemsanity spec's block-collision table and is clear of the trial+token family
below it, the relic-perfect block at 35012400, the item-box block at 35014000 and
the podium blocks at 35015000 / 35015100.

The 48 letter ITEMS are ordinary `data/items.json` entries at indexes 139-186
(`35010139`-`35010186`), track-major then C/T/R, the same order as the locations
here. They are items, not locations, so they are not this class's to register --
`ITEM_NAMES` below exists so the two orders provably cannot drift, and the tests
assert it against the live item table.

FROZEN-NAME WARNING. These names ride the single 0.2.0 datapackage bump (#177).
After that bump they are permanent, and their ids can never move.

NAMES LAND INERT. `created_location_names` returns nothing, unconditionally, and
every letter item carries `count: 0`, because no option creates either yet -- the
0.2.0 freeze mints names, not features.
"""
import json
import pkgutil

from .location_class import LocationClass

# Additive block for the 48 letter checks, stride 3 per track.
LETTERSANITY_CODE_BASE = 35012500

# The three letters, in the order the game spells them and the order this block's
# codes run. Frozen: it is the within-track stride order.
LETTERS = ("C", "T", "R")


def _token_challenge_tracks():
    """The 16 CTR Token Challenge tracks in canonical (token-code) order, read
    from data/locations.json so this block's codes/order can never drift from the
    token block it parallels. #148 scopes lettersanity to exactly the tracks that
    have a CTR Token Challenge, which is the 16 trophy tracks."""
    data = json.loads(
        pkgutil.get_data(__package__, "data/locations.json").decode("utf-8")
    )
    tt = [(loc["code"], loc["region"]) for loc in data
          if loc["name"].endswith(": CTR Token Challenge") and loc["code"] is not None]
    return [region for _code, region in sorted(tt)]


# Canonical, stable track order (module import time). 16 entries.
LETTER_TRACKS = _token_challenge_tracks()
from .trial_trophy import TRIAL_TRACKS
ALL_LETTER_TRACKS = tuple(LETTER_TRACKS) + TRIAL_TRACKS


def eligible_letter_tracks(options):
    """Mode-admitted retail tracks, preserving the frozen 16-row prefix.

    Used by the extension's selection/pool/rules/wire integration. Trial relic
    and Trophy access alone never admit letter items or checks.
    """
    from .trial_trophy import TRIAL_TRACKS, TRIAL_TROPHY_CLASS
    from .cortex_vortex_track import dropped_track
    created = set(TRIAL_TROPHY_CLASS.created_location_names(options))
    tracks = tuple(LETTER_TRACKS) + tuple(
        track for track in TRIAL_TRACKS
        if TRIAL_TROPHY_CLASS.ctr_location_name(track) in created)
    # A destination the Cortex Vortex track dropped loses its CTR Token
    # Challenge, so its letters (checks and items) leave the seed with it.
    # Cortex Vortex's own letters are that class's, not this retail family's.
    dropped = dropped_track(options) if options is not None else None
    return tuple(track for track in tracks if track != dropped)


def item_name(track: str, letter: str) -> str:
    """AP ITEM name for a track's letter, e.g. 'Letter C (Crash Cove)'.

    Follows the existing per-character item convention in data/items.json
    ("Progressive Boost (Crash Bandicoot)"): base name, qualifier in parentheses.
    Deliberately NOT the same string as the location name -- items and locations
    live in separate namespaces, but a hint reading "Letter C (Crash Cove)" for
    the item and "Crash Cove: Letter C" for the place is unambiguous about which
    kind of thing it is talking about.
    """
    return f"Letter {letter} ({track})"


#: The 48 letter item names in frozen order (track-major, then C/T/R). Mirrors
#: data/items.json indexes 139-186; asserted against the live item table by
#: test_lettersanity so the two can never drift.
ITEM_NAMES = tuple(item_name(track, letter)
                   for track in LETTER_TRACKS for letter in LETTERS)
ALL_ITEM_NAMES = ITEM_NAMES + tuple(item_name(track, letter)
                                  for track in TRIAL_TRACKS for letter in LETTERS)


class LettersanityLocationClass(LocationClass):
    """The 48 letter checks as a `LocationClass` (#176)."""

    key = "lettersanity"
    display_name = "Lettersanity"
    code_blocks = (LETTERSANITY_CODE_BASE,)

    def all_locations(self):
        out = []
        for ti, track in enumerate(ALL_LETTER_TRACKS):
            for li, letter in enumerate(LETTERS):
                out.append((self.location_name(track, letter),
                            LETTERSANITY_CODE_BASE + ti * len(LETTERS) + li,
                            track))
        return out

    def location_name(self, track: str, letter: str) -> str:
        """AP location name for a track's letter, e.g. 'Crash Cove: Letter C'."""
        return f"{track}: Letter {letter}"

    def created_location_names(self, options):
        if options is None or not hasattr(options, "lettersanity") or int(options.lettersanity.value) not in (1, 2):
            return []
        selected = getattr(options, "_lettersanity_selected", {})
        return [self.location_name(track, letter) for track in eligible_letter_tracks(options)
                for letter in LETTERS if letter in selected.get(track, ())]

    def wire_block(self, options):
        live = set(self.created_location_names(options))
        return {"mode": int(options.lettersanity.value),
                "letters_per_track": int(options.letters_per_track.value),
                "locations": {str(TRACK_LEVEL_IDS[track]): [
                    self.code_for(track, letter) if self.location_name(track, letter) in live else -1
                    for letter in LETTERS] for track in eligible_letter_tracks(options)}}


#: The registered lettersanity class. `Locations.py` registers this instance.
LETTERSANITY_CLASS = LettersanityLocationClass()

_pads = json.loads(pkgutil.get_data(__package__, "data/warp_pad_ids.json").decode("utf-8"))["pads"]
TRACK_LEVEL_IDS = {name[:-len(" Warp Pad")]: meta["level_id"] for name, meta in _pads.items()
                   if name[:-len(" Warp Pad")] in set(ALL_LETTER_TRACKS)}


def restore_letter_selection(options, block, mode, count):
    """Validate slot-owned retail/trial wire identities before restoring UT."""
    from collections.abc import Mapping
    if type(mode) is not int or mode not in range(4) or type(count) is not int or count not in (1, 2, 3):
        raise ValueError("invalid lettersanity mode/count")
    if not isinstance(block, Mapping) or type(block.get("mode", mode)) is not int or block.get("mode", mode) != mode:
        raise ValueError("lettersanity block mode mismatch")
    rows = block.get("locations", {})
    if not isinstance(rows, Mapping):
        raise ValueError("lettersanity locations must be a mapping")
    admitted = eligible_letter_tracks(options)
    by_id = {str(TRACK_LEVEL_IDS[track]): track for track in admitted}
    if mode and set(rows) != set(by_id):
        raise ValueError("lettersanity rows do not match admitted tracks")
    selected = {}
    known = {str(lid) for lid in TRACK_LEVEL_IDS.values()}
    for lid, codes in rows.items():
        if lid not in known or not isinstance(codes, (list, tuple)) or len(codes) != 3:
            raise ValueError("invalid lettersanity row")
        if any(type(code) is not int for code in codes):
            raise ValueError("letter addresses must be integers")
        track = by_id.get(lid)
        if track is None:
            if mode or any(code != -1 for code in codes):
                raise ValueError("unadmitted letter track")
            continue
        letters = []
        for letter, code in zip(LETTERS, codes):
            if code != -1:
                if mode not in (1, 2) or code != LETTERSANITY_CLASS.code_for(track, letter):
                    raise ValueError("letter address does not belong to track")
                letters.append(letter)
        if mode in (1, 2) and len(letters) != count:
            raise ValueError("letter selection count mismatch")
        selected[track] = tuple(letters)
    return selected
