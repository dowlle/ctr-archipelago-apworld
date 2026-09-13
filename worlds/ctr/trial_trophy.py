"""Trophy Races on the two trial tracks -- Slide Coliseum and Turbo Track (#203).

WHAT THIS CLASS CHECKS AND WHERE THE SIGNAL COMES FROM. Finishing 1st in a
Trophy Race launched from the Slide Coliseum or Turbo Track adventure warp pad.
No Trophy item is granted: the 16-trophy economy is unchanged, boss garage
thresholds stay at 4/8/12/16 and every pad requirement count is untouched. The
reward comes from the normal multiworld pool like any other check.

WHO OWNS THE SEMANTICS. The apworld owns the names, the option and the rule;
native owns the pad behaviour -- `game/232/AH_WarpPad.c:570-581` unconditionally
sets `AddBitsConfig0 |= RELIC_RACE` for adventure trial-pad level IDs 16 and 17,
which is the branch that makes those two pads relic-only today. Neither half is
built here.

WHY THIS IS ITS OWN CLASS RATHER THAN TWO ROWS IN data/locations.json. Adding
"Slide Coliseum: Trophy Race" and "Turbo Track: Trophy Race" to the static table
would silently mint FOURTEEN more names: `podium.py._trophy_tracks()` derives its
canonical 16-track order by scanning data/locations.json for names ending in
": Trophy Race", so two more static rows would grow the podium superset from 112
to 126 rungs and extend a shipped class's canonical track order. Registering
these two through the class registry instead keeps `_trophy_tracks()` reading
exactly 16 and mints exactly the two names #203 asks for. The disjointness check
in Locations.py makes the mistake loud if anyone later adds them statically as
well: the import fails rather than silently overwriting an id.

DATAPACKAGE STABILITY. This class claims the additive block 35016200, stride 1 in
TRIAL_TRACKS order, and registers both names UNCONDITIONALLY. It sits clear of
itemsanity's 35016000-021 and the wumpa 35016100 code.

FROZEN-NAME WARNING. These names ride the single 0.2.0 datapackage bump (#177).
After that bump they are permanent, and their ids can never move.

The two Trophy identities shipped in 0.2.0. Issue #203 activates them through
one independent three-state option per trial track. The third state also creates
the paired CTR Challenge; because that state includes the Trophy Race, CTR-only
configuration is unrepresentable.
"""
from .location_class import LocationClass

# Additive block for the two trial-track trophy races, stride 1.
TRIAL_TROPHY_CODE_BASE = 35016200
TRIAL_CTR_CODE_BASE = 35016210

#: The two adventure trial tracks, in level-ID order (Slide Coliseum 16, Turbo
#: Track 17) -- the same relative order they hold at the tail of the 18-track
#: relic canon. FROZEN: it is this block's stride order.
TRIAL_TRACKS = ("Slide Coliseum", "Turbo Track")


class TrialTrophyLocationClass(LocationClass):
    """The two trial-track Trophy Races as a `LocationClass` (#176)."""

    key = "trial_trophy"
    display_name = "Trial Track Trophy Races"
    code_blocks = (TRIAL_TROPHY_CODE_BASE, TRIAL_CTR_CODE_BASE)

    def all_locations(self):
        rows = []
        for ti, track in enumerate(TRIAL_TRACKS):
            rows.append((self.location_name(track),
                         TRIAL_TROPHY_CODE_BASE + ti, track))
            rows.append((self.ctr_location_name(track),
                         TRIAL_CTR_CODE_BASE + ti, track))
        return rows

    def location_name(self, track: str) -> str:
        """AP location name for a trial track's trophy race, e.g.
        'Slide Coliseum: Trophy Race'. Matches the shipped suffix on the 16
        static trophy races deliberately: it is the same event on a track that
        did not previously host it."""
        return f"{track}: Trophy Race"

    def ctr_location_name(self, track: str) -> str:
        return f"{track}: CTR Token Challenge"

    def created_location_names(self, options):
        from .cortex_vortex_track import dropped_track
        names = []
        option_names = ("slide_coliseum_races", "turbo_track_races")
        # A trial the Cortex Vortex track dropped has no pad, so its races
        # leave the seed whatever its own option says.
        dropped = dropped_track(options) if options is not None else None
        for track, option_name in zip(TRIAL_TRACKS, option_names):
            if track == dropped:
                continue
            mode = int(getattr(getattr(options, option_name, 0), "value",
                               getattr(options, option_name, 0)))
            if mode >= 1:
                names.append(self.location_name(track))
            if mode >= 2:
                names.append(self.ctr_location_name(track))
        return names


#: The registered trial-trophy class. `Locations.py` registers this instance.
TRIAL_TROPHY_CLASS = TrialTrophyLocationClass()
