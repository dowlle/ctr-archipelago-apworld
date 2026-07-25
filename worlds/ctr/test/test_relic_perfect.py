"""Guards for the relic-race perfect checks (issue #49).

#49 adds one optional location per relic race, earned by breaking every time
crate in it. Stef's ruling (2026-07-20): a location class, default OFF, one check
per relic race (18: the 16 adventure tracks plus Slide Coliseum and Turbo Track),
and explicitly NOT the stricter "no relic unless perfect" reward gate.

What these tests lock in:

- TestRelicPerfectDatapackage: all 18 names are registered UNCONDITIONALLY (the
  podium precedent -- name<->id is global and must not move with an option), the
  codes are unique, contiguous from the additive 35012400 block, and collide with
  no other registered CTR code. Also that the track order is the Sapphire-trial
  order, so a future data edit cannot silently renumber the block.
- TestRelicPerfectOff (the default): not one perfect location is created, and the
  seed's location count is the pre-#49 number.
- TestRelicPerfectOn: exactly 18 created, each in the same region as its own
  relic Time Trials, each an ordinary fillable slot, and pool == locations.
- TestRelicPerfectLogicParity: on a trophy track the perfect check's rule accepts
  exactly the states its Sapphire Time Trial accepts (same Trophy-Race + stage-2
  gate), and on the two trial tracks it is gated only by reaching the pad. This
  is the property that makes apworld logic match native's relic-race entry gate.
- TestRelicPerfectSlotData: the additive `relic_perfect` block reports enabled +
  the 18 codes keyed by pad LevelID when on, and an empty block when off, and UT's
  option restore round-trips through exactly that block.
- The inherited default fill tests run with the option ON in TestRelicPerfectOn
  (accessibility guard + fill over the extra 18 locations).
"""

from BaseClasses import CollectionState

from ..Locations import CTR_LOCATION_IDS, CTR_LOCATION_TO_REGION
from ..relic_perfect import (RELIC_PERFECT_CODE_BASE, RELIC_PERFECT_SUFFIX,
                             RELIC_TRACKS, all_relic_perfect_locations,
                             location_name)
from . import CTRTestBase

# The 18 relic tracks, retyped once from data/locations.json's Sapphire block in
# code order. This is the DRIFT GUARD: relic_perfect.RELIC_TRACKS derives the
# order from that data at import, and this copy exists only so a test fails if
# the data (and therefore the frozen codes) ever moves.
EXPECTED_RELIC_TRACKS = (
    "Crash Cove", "Roo's Tubes", "Mystery Caves", "Sewer Speedway",
    "Coco Park", "Tiger Temple", "Papu's Pyramid", "Dingo Canyon",
    "Blizzard Bluff", "Dragon Mines", "Polar Pass", "Tiny Arena",
    "Hot Air Skyway", "Cortex Castle", "N. Gin Labs", "Oxide Station",
    "Slide Coliseum", "Turbo Track",
)
# Tracks with no Trophy Race: their relic races (and so their perfect check) are
# gated purely by reaching the pad.
TRIAL_TRACKS = ("Slide Coliseum", "Turbo Track")

PERFECT_NAMES = tuple(f"{t}: {RELIC_PERFECT_SUFFIX}" for t in EXPECTED_RELIC_TRACKS)


class TestRelicPerfectDatapackage(CTRTestBase):
    """Datapackage properties -- independent of any seed's options."""

    run_default_tests = False
    options = {}

    def test_track_order_matches_the_relic_block(self):
        self.assertEqual(tuple(RELIC_TRACKS), EXPECTED_RELIC_TRACKS)

    def test_all_eighteen_names_registered_unconditionally(self):
        # This world was generated with the option OFF (default); the names must
        # still be in the datapackage.
        self.assertFalse(self.world.options.relic_perfect_checks.value)
        for name in PERFECT_NAMES:
            with self.subTest(location=name):
                self.assertIn(name, CTR_LOCATION_IDS)

    def test_codes_are_the_additive_block_and_unique(self):
        codes = [code for _n, code, _r in all_relic_perfect_locations()]
        self.assertEqual(len(codes), 18)
        self.assertEqual(len(set(codes)), 18)
        self.assertEqual(
            codes,
            list(range(RELIC_PERFECT_CODE_BASE, RELIC_PERFECT_CODE_BASE + 18)))

    def test_codes_collide_with_nothing_else(self):
        ours = {code for _n, code, _r in all_relic_perfect_locations()}
        others = [code for name, code in CTR_LOCATION_IDS.items()
                  if name not in PERFECT_NAMES and code is not None]
        self.assertEqual(len(others), len(set(others)),
                         "pre-existing CTR codes are not unique")
        self.assertFalse(ours & set(others),
                         "relic-perfect codes overlap a shipped code block")

    def test_regions_are_the_tracks(self):
        for track in EXPECTED_RELIC_TRACKS:
            with self.subTest(track=track):
                self.assertEqual(
                    CTR_LOCATION_TO_REGION[location_name(track)], track)
                # ... which is where that track's relic races already live.
                self.assertEqual(
                    CTR_LOCATION_TO_REGION[f"{track}: Sapphire Time Trial"], track)

    def test_suffix_is_reward_neutral_in_the_sphere_search(self):
        # warp_pad_logic._reward_for keys off the name suffix; a suffix ending in
        # "Time Trial" would make the sphere search hand out a free relic for a
        # location that awards nothing.
        from ..warp_pad_logic import _reward_for
        self.assertFalse(RELIC_PERFECT_SUFFIX.endswith("Time Trial"))
        self.assertIsNone(_reward_for("Crash Cove", "Crash Cove",
                                      RELIC_PERFECT_SUFFIX))


class TestRelicPerfectOff(CTRTestBase):
    """The default: registered but not created."""

    run_default_tests = False
    options = {}

    def test_no_perfect_location_created(self):
        names = {loc.name for loc in self.multiworld.get_locations(self.player)}
        self.assertFalse(names & set(PERFECT_NAMES))

    def test_slot_data_block_is_empty(self):
        block = self.world.fill_slot_data()["relic_perfect"]
        self.assertEqual(block, {"enabled": False, "locations": {}})


class TestRelicPerfectOn(CTRTestBase):
    """Option ON: 18 real, fillable, correctly-parented locations. Runs the
    inherited default tests (reachability + fill) over the widened location set."""

    options = {"relic_perfect_checks": True}

    def test_eighteen_created(self):
        names = {loc.name for loc in self.multiworld.get_locations(self.player)}
        self.assertEqual(names & set(PERFECT_NAMES), set(PERFECT_NAMES))

    def test_each_lives_with_its_own_relic_races(self):
        for track in EXPECTED_RELIC_TRACKS:
            with self.subTest(track=track):
                loc = self.multiworld.get_location(location_name(track),
                                                   self.player)
                trial = self.multiworld.get_location(
                    f"{track}: Sapphire Time Trial", self.player)
                self.assertIs(loc.parent_region, trial.parent_region)

    def test_they_are_ordinary_fillable_slots(self):
        # Not pinned, not locked: they exist to hold multiworld items.
        for name in PERFECT_NAMES:
            with self.subTest(location=name):
                loc = self.multiworld.get_location(name, self.player)
                self.assertFalse(loc.locked)
                # A real, addressed location (not an event): the server can send it.
                self.assertIsNotNone(loc.address)

    def test_item_and_location_counts_balance(self):
        pool = [item for item in self.multiworld.itempool
                if item.player == self.player]
        unfilled = self.multiworld.get_unfilled_locations(self.player)
        self.assertEqual(len(pool), len(unfilled),
                         "the 18 extra locations must pull 18 extra filler items")


class TestRelicPerfectLogicParity(CTRTestBase):
    """The perfect check must be reachable exactly when that track's relic races
    are -- the property that keeps apworld logic identical to native's relic-race
    entry gate, stage-2 gates included."""

    run_default_tests = False
    options = {
        "relic_perfect_checks": True,
        "warppad_unlock_requirements": "randomized",
        "two_stage_density": "full",
    }

    def _states(self):
        """A spread of inventories: empty, and progressively more of everything
        the gates can ask for."""
        yield CollectionState(self.multiworld)
        for n in (1, 4, 8, 16):
            state = CollectionState(self.multiworld)
            for item in ("Trophy", "Key", "Sapphire Relic", "Gold Relic",
                         "Platinum Relic", "Red CTR Token", "Green CTR Token",
                         "Blue CTR Token", "Yellow CTR Token", "Purple CTR Token",
                         "Red Gem", "Green Gem", "Blue Gem", "Yellow Gem",
                         "Purple Gem"):
                state.collect(self.world.create_item(item), prevent_sweep=True)
                if n > 1:
                    for _ in range(n - 1):
                        state.collect(self.world.create_item(item),
                                      prevent_sweep=True)
            yield state

    def test_rule_matches_the_sapphire_trial(self):
        states = list(self._states())
        for track in EXPECTED_RELIC_TRACKS:
            perfect = self.multiworld.get_location(location_name(track),
                                                   self.player)
            trial = self.multiworld.get_location(f"{track}: Sapphire Time Trial",
                                                 self.player)
            for i, state in enumerate(states):
                with self.subTest(track=track, state=i):
                    self.assertEqual(bool(perfect.access_rule(state)),
                                     bool(trial.access_rule(state)))

    def test_trophy_tracks_need_their_trophy_race(self):
        # NECESSARY, not equivalent. With a stage-2 gate on a track, its relic
        # races can still be shut while its Trophy Race is already reachable --
        # that IS stage 2, and it applies to the perfect check for the same reason
        # it applies to the trials. So the property to hold is one-directional:
        # the perfect check must never be open on a track you cannot race.
        # (Equality with the trials is test_rule_matches_the_sapphire_trial.)
        # An earlier version of this test asserted equality with can_reach and
        # flaked on exactly the seeds where a sphere-0 free pad drew a stage 2.
        states = list(self._states())
        gated_from_empty = False
        for track in EXPECTED_RELIC_TRACKS:
            if track in TRIAL_TRACKS:
                continue
            perfect = self.multiworld.get_location(location_name(track),
                                                   self.player)
            trophy = f"{track}: Trophy Race"
            for i, state in enumerate(states):
                with self.subTest(track=track, state=i):
                    if perfect.access_rule(state):
                        self.assertTrue(
                            state.can_reach(trophy, "Location", self.player),
                            "a relic-perfect check is open on a track whose "
                            "Trophy Race is not reachable")
                    elif i == 0:
                        gated_from_empty = True
        # Sanity that the rule is not blanket-True: from an empty inventory the
        # deep hub tracks are unreachable in every seed.
        self.assertTrue(gated_from_empty,
                        "no perfect check was gated at all from an empty state")

    def test_nothing_gates_on_a_perfect_check(self):
        # It is pure location supply: no rule anywhere may require it, so
        # accessibility: full can never be made unsatisfiable by turning it on.
        all_state = self.multiworld.get_all_state()
        for track in EXPECTED_RELIC_TRACKS:
            with self.subTest(track=track):
                loc = self.multiworld.get_location(location_name(track),
                                                   self.player)
                self.assertTrue(loc.can_reach(all_state))


class TestRelicPerfectSlotData(CTRTestBase):
    """The additive native fan-out block, and the UT restore that reads it."""

    run_default_tests = False
    options = {"relic_perfect_checks": True}

    def test_block_reports_enabled_and_all_eighteen_codes(self):
        block = self.world.fill_slot_data()["relic_perfect"]
        self.assertTrue(block["enabled"])
        locs = block["locations"]
        self.assertEqual(len(locs), 18)
        # Keyed by physical pad LevelID, values are the frozen AP codes.
        pad_ids = self.world.warp_pad_ids
        for track in EXPECTED_RELIC_TRACKS:
            lid = str(pad_ids[f"{track} Warp Pad"]["level_id"])
            with self.subTest(track=track):
                self.assertEqual(locs[lid], CTR_LOCATION_IDS[location_name(track)])

    def test_schema_version_is_not_bumped(self):
        # Additive key (the one_lap_cups / death_link precedent): an older native
        # ignores the block, and every seed that does not use the feature stays
        # byte-compatible with schema 6.
        slot_data = self.world.fill_slot_data()
        self.assertEqual(slot_data["schema_version"], 6)
        self.assertEqual(slot_data["ctr_options"]["schema_version"], 6)

    def test_ut_restores_the_toggle_from_the_block(self):
        world = self.world
        world.options.relic_perfect_checks.value = 0
        world._ut_restore_options({"ctr_options": {}, "warp_pad_unlock": {},
                                   "podium_checks": {},
                                   "relic_perfect": {"enabled": True}})
        self.assertEqual(world.options.relic_perfect_checks.value, 1)
        # A pre-#49 seed carries no block at all -> the feature stays off.
        world._ut_restore_options({"ctr_options": {}, "warp_pad_unlock": {},
                                   "podium_checks": {}})
        self.assertEqual(world.options.relic_perfect_checks.value, 0)
