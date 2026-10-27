"""Item-pool construction for the CTR world (split out of __init__.py, issue #309).

Pure move: every function here was a method body on ctrAPWorld. The World
class keeps the public methods and delegates to these functions with itself
as `world`, so call order, RNG draws and results are unchanged.
"""

import json
import pkgutil
from typing import Dict

from BaseClasses import ItemClassification
from Options import OptionError

from . import (characters, cortex_vortex_track, item_boxes, item_supply, spoiler_items,
               lettersanity, progressive_capability, tizi_helper, traps,
               turbo_grant, wumpa_family)
from .custom_lettersanity import CUSTOM_LETTERSANITY_CLASS
from .custom_tracks import replacement_trophy_location, resolved_custom_tracks
from .elastic_bounds import estimated_filler_reserve
from .item_boxes import ITEM_BOX_CLASS
from .Items import load_item_table
from .itemsanity import ITEM_NAMES, WEAPONS
from .Options import OxideGoal
from .relic_tiers import RELIC_TIERS
from .tizi_helper import TIZI_HELPER_ITEM
from .turbo_grant import TURBO_GRANT_ITEM
from .Types import ctrAPItem

# Comfort-only issues #14/#15 pack. It stays atomic when a reduced location
# set cannot host all five, rather than emitting a seed-dependent subset.
SURFACE_ITEM_NAMES = frozenset({
    "Ignore Grass", "Ignore Dirt", "Ignore Snow", "Ignore Water", "Ignore Ice",
})


def create_item(world, name: str) -> "ctrAPItem":
    item_id: int = world.item_name_to_id[name]
    classification = world._item_data_by_name[name]["classification"]
    # Honest per-seed relic classification (vanilla-fill lever 1).
    # data/items.json marks every relic "progression" unconditionally, but in a
    # vanilla-warp-pad seed whose goal/accessibility does not depend on a relic
    # tier, that tier gates nothing -- yet the ordered fill still treats it as
    # progression, inflating the pool to exactly the location count (zero slack)
    # and cornering fill_restrictive on the deepest currency. Downgrade such a
    # tier to "useful" so it leaves the ordered fill (placed by remaining_fill).
    # The map is a pure function of options; see _relic_progression_map.
    relic_prog = getattr(world, "_ctr_relic_prog", None)
    if relic_prog is not None and relic_prog.get(name) is False:
        classification = ItemClassification.useful
    # Honest per-seed BOOST classification, the same lever in the other
    # direction. #145 Itemsanity is the first logic reader of a capability
    # tier: its Turbo checks require one received Progressive Boost when
    # the chain is randomized (Decision 2 ruling, 2026-08-10). Logic state
    # only tracks progression items, so the gate is only real if the chain
    # is progression in exactly those seeds -- left `useful` (the #12/#13
    # shape), the Turbo checks sit permanently outside logic and fill
    # forbids progression/useful there, which surfaced as FillErrors in
    # the 5,000-run default fuzz arm. Every other seed keeps the frozen
    # `useful` classification from data/items.json.
    # #109 box slots are the second reader: boost-gated slots exist in
    # every box seed, and the hard-knowledge slots additionally read the
    # three stat chains (the hard-tier general rule), so those chains
    # upgrade too -- but ONLY at hard, because no easier tier creates a
    # stats-reading slot.
    # The USF finish gate (usf_finish.py, ruled 2026-08-12) is the
    # third reader and the one that makes the boost upgrade UNCONDITIONAL:
    # Hot Air Skyway's Trophy Race is a static location present in every
    # seed, so every randomized-boost seed reads the chain now, whatever
    # itemsanity and box locations are set to. Left `useful`, that track's
    # finish -- and its time trials, token challenge and finish rungs --
    # would sit permanently outside logic, the same FillError class the
    # #145 upgrade was written for. The stat chains keep their narrower
    # condition: no rule outside the hard box tier reads them.
    _boost_mode = int(world.options.progressive_boost.value)
    _boost_names = ({progressive_capability.BOOST_CHAIN} if _boost_mode == 1
                    else {progressive_capability.boost_item_name(c)
                          for c in progressive_capability.ROSTER}
                    if _boost_mode == 2 else set())
    if name in _boost_names:
        classification = ItemClassification.progression
    _stats_mode = int(world.options.progressive_stats.value)
    _stat_names = (set(progressive_capability.STAT_CHAINS)
                   if _stats_mode == 1 else
                   {progressive_capability.stat_item_name(chain, character)
                    for character in progressive_capability.ROSTER
                    for chain in progressive_capability.STAT_CHAINS}
                   if _stats_mode == 2 else set())
    if (name in _stat_names
            and ITEM_BOX_CLASS.is_enabled(world.options)
            and int(world.options.shortcut_knowledge.value) == item_boxes.SK_HARD):
        classification = ItemClassification.progression
    # Honest per-seed CHARACTER classification (R17), the same lever again.
    # data/items.json freezes all 16 racers as `useful`; a racer-locked seed
    # has pads whose access rule reads one, so in exactly those seeds the
    # unlock items are genuine progression. Locks off leaves them `useful`,
    # which is both the correct AP semantics for an item that gates nothing
    # and a deliberate relaxation of an already ~98%-progression pool.
    if name in characters.ROSTER_CHARACTER_ID:
        classification = characters.unlock_classification(world)
    return ctrAPItem(
        name=name,
        classification=classification,
        code=item_id,
        player=world.player,
    )


def relic_progression_map(world) -> Dict[str, bool]:
    """Which relic tiers are genuine PROGRESSION in this seed (True) vs merely
    USEFUL (False). A relic tier is progression only when some reachable-required
    location or the goal actually depends on owning it.

    Enumeration of the (warp-pad mode, goal, accessibility) matrix -- vanilla
    mode is the ONLY case that ever downgrades:

    * Randomized / random_without_4_keys (mode 1/2): ALL relics stay
      progression. The sphere search may assign a relic entry or stage-2
      requirement to ANY pad, so relics must remain orderable by fill; the
      randomized path's own pre_fill relax-not-pin guard handles fillability.
      No behavioural change from today.
    * Vanilla mode (mode 0) -- two relic-count gates exist: the Slide
      Coliseum pad exit (has('Sapphire Relic', 10), data/world.json, lowered
      to the Sapphires created when fewer exist, 2026-10-01) and
      N. Oxide's Final Challenge, whose gate follows the CONFIGURED
      oxide_final_challenge_unlock mode + count in every seed (issue #53,
      Rules.add_oxide_final_challenge_rule -- the world.json 18-Sapphire
      text is legacy and overridden). So:
        - Sapphire: progression iff accessibility == full (the fixed Slide
          Coliseum gate must be reachable) OR the goal makes you reach + win
          Oxide's Final Challenge (oxidefinal). Else useful, unless it is a
          satisfying tier of the configured mode (next rule).
        - Any tier satisfying the configured mode (created > 0): progression
          iff accessibility == full (the Final Challenge location must be
          reachable) OR oxide_goal == final. Else useful.
        - A tier that is neither: useful.
    """
    o = world.options
    prog = {"Sapphire Relic": True, "Gold Relic": True, "Platinum Relic": True}
    # Universal Tracker (issue #29): read the seed's RESOLVED classification off
    # the wire rather than trying to recompute it from inputs that do not travel
    # (the per-tier progression sliders are not emitted). This map is not merely
    # cosmetic on the UT path: CollectionState.collect ignores non-advancement
    # items, so a tier the seed classified `useful` can never satisfy a has()
    # gate server-side. Assuming "all tiers progression" therefore made UT open
    # the vanilla Slide Coliseum pad (has('Sapphire Relic', 10), data/world.json)
    # on seeds where the server never can -- UT then reported its three time
    # trials in logic against a sphere that will never contain them (the ~12.6%
    # UT-check failures, all vanilla + accessibility:minimal + non-oxidefinal
    # seeds). The earlier comment here was right that no vanilla gate names
    # gold/platinum, but missed the Sapphire one.
    #
    # BACKWARDS COMPATIBILITY: seeds generated before `relic_progression` was
    # emitted carry no such key. For those, fall back to the historical
    # all-progression behaviour -- no worse than before, and it keeps UT usable
    # against already-rolled seeds.
    _pt = getattr(world.multiworld, "re_gen_passthrough", {}).get(world.game)
    if _pt:
        wire = (_pt.get("ctr_options") or {}).get("relic_progression")
        if isinstance(wire, dict):
            return {tier: bool(wire.get(tier, True)) for tier in prog}
        return prog
    if o.warppad_unlock_requirements.value != 0:
        return prog  # randomized modes: any pad may gate on any relic tier
    access_full = o.accessibility.value == 0  # Accessibility.option_full == 0
    # Base vanilla-mode classification: the fixed vanilla LOCATION gate that
    # names a relic is Sapphire (Slide Coliseum has('Sapphire Relic', 10)),
    # so Sapphire is progression exactly when every location must be reachable
    # (accessibility: full). Gold/Platinum gate no FIXED vanilla location.
    prog["Sapphire Relic"] = access_full
    prog["Gold Relic"] = False
    prog["Platinum Relic"] = False
    # N. Oxide's Final Challenge (issue #53): the location's gate reads the
    # CONFIGURED oxide_final_challenge_unlock mode + count in every seed
    # (Rules.add_oxide_final_challenge_rule, native parity), so under
    # accessibility 'full' the satisfying tiers must be progression for the
    # location to be reachable -- the same created>0 respect as the goal
    # branch below (a tier the player opted out of stays useful and the
    # forced_options supply guard raises instead). Kept in lockstep with
    # raise_if_full_accessibility_needs_more_sapphires_than_created.
    # Issue #320 acceptance 4: with `oxide_goal: disabled` the Final
    # Challenge LOCATION is never created, so accessibility 'full' has no
    # relic gate here to make reachable and the configured unlock mode +
    # count must not steer item classification. The Slide Coliseum
    # sapphire gate above is a separate, still-live relic gate and is
    # unaffected. Kept in lockstep with the matching skips in
    # forced_options.py's two relic-supply guards.
    if access_full and OxideGoal.oxide_content_present(o.oxide_goal.value):
        for tier in world._oxide_goal_tiers():
            if world._ctr_relic_created.get(tier, 0) > 0:
                prog[tier] = True
    # Oxide-final goal (issue #23; #152 C4: generalized from the legacy
    # `goal == oxidefinal` value to the composed `oxide_goal == final`
    # condition -- this branch and forced_options.py's
    # raise_if_oxidefinal_goal_has_no_progression_tier guard must move in
    # lockstep, see that guard's docstring): the relic tiers that satisfy
    # the configured mode+count must be progression so fill, the spoiler
    # playthrough, and beatability chase the REAL goal (not the old
    # hard-coded 18 Sapphire). Respect the per-tier exact counts (issue
    # #171: was a percentage slider, now a created-location count) -- a
    # satisfying tier with 0 created stays out and is caught by
    # generate_early's guard rather than silently forced.
    if o.oxide_goal.value == OxideGoal.option_101_percent:
        # Sapphire is progression on ANY oxide-final seed (mode-independent):
        # once the goal makes any relic tier progression, fill may place a
        # progression relic behind the Slide Coliseum sapphire gate (the fixed
        # has('Sapphire Relic', 10) vanilla exit rule) -- Sapphire must stay
        # progression to keep those locations reachable. This mirrors the
        # pre-#23 goal, which was itself 18 Sapphire and always set this.
        # (The Final Challenge location gate itself is mode-aware since
        # issue #53, see the access_full block above.)
        prog["Sapphire Relic"] = True
        for tier in world._oxide_goal_tiers():
            if world._ctr_relic_created.get(tier, 0) > 0:
                prog[tier] = True
    return prog


def create_items(world):
    if hasattr(world, "ctr_content_plan"):
        from . import content_plan
        content_plan.create_items(world)
        return
    player = world.player
    mw = world.multiworld
    pool = []

    # Per-seed relic classification (lever 1); consumed by create_item for every
    # relic created below (pool + slider/goal pins). Computed once here so the
    # whole create_items pass sees a single consistent map.
    world._ctr_relic_prog = world._relic_progression_map()

    # Vanilla-fill lever 2 (four early Keys in vanilla warp-pad mode with
    # Keys shuffled) was removed on 2026-10-02. AP locks early items into
    # the slot's starting checks, so on a narrow start the Keys took every
    # one of them and left no spot for the item that opens the next check
    # (fuzz 36720, 2026-10-01). Measured 2026-10-02 on 2,986 solo seeds and
    # 1,002 two-slot rooms that 0.2.3 accepts: with no early Key every one
    # generates and the backstop never fires (it fired 6 times with four).

    # Itemsanity's native crate filter returns Wumpa when the player has no
    # received weapon. Seed one weapon type into early fill so an enabled
    # seed has an opening weapon without granting it as starting
    # inventory. One, not two: with the narrowest admitted start (two
    # checks, sphere0_guard.MIN_STARTING_CHECKS) one starting check stays
    # free. The draw still takes a count of one or two and a sample of that
    # size, exactly as before, so every later draw from world.random is
    # unchanged; only the first sampled weapon is used. early_items is a
    # fill-order hint: it changes neither what is required nor any emitted
    # slot_data value. No RNG is consumed while the toggle is off.
    if world.options.itemsanity.value:
        early_count = world.random.randint(1, 2)
        weapon = world.random.sample(WEAPONS, early_count)[0]
        mw.early_items.setdefault(player, {})[weapon] = 1

    world._install_goal(player)

    # --- Relic-tier exact-count removal (issue #171 conversion; issue #28
    # R1: removal, not pinning) ---
    # generate_early's relic draw (relic_tiers.draw_relic_tier_keep) already
    # decided exactly which of each tier's 18 Time Trial locations this seed
    # creates (world._ctr_relic_keep), and Regions.create_regions already built
    # Location objects for only those -- a below-count slot was never created
    # at all, so unlike the pinned-vanilla block this replaces (used to sit
    # here, __init__.py:849-902 on origin/main), there is no location left to
    # place_locked_item onto. _relic_locked below exists purely so the general
    # item-pool loop two blocks down creates (18 - n_created) fewer of that
    # relic -- the exact same "keep item count == location count" invariant
    # the old block's own n_locked bookkeeping maintained, just driven by the
    # draw's created count instead of a per-location pin roll. The Turbo Track
    # comfort guard is enforced inside the draw itself now (excluded from the
    # sample pool, relic_tiers.draw_relic_tier_keep), so there is nothing
    # left for create_items to force here.
    _relic_locked = {
        _relic_item: 18 - world._ctr_relic_created.get(_relic_item, 18)
        for _tier_label, _relic_item, _opt_name in RELIC_TIERS
    }

    # --- Gem & Key placement toggles (item #5) ---
    # Default OFF = pinned vanilla (each Gem locked to its Gem Cup, each Key
    # locked to its Boss Race -> out of the multiworld pool). ON = the item
    # enters the shuffled pool and its vanilla location becomes a normal check.
    # Track n_locked per item name so the general pool below creates
    # (count - n_locked) of it, keeping item count == location count.
    # Issue #152 C6 (drift fix, folded into the composition per the
    # dossier's Q30 ruling): renamed from the legacy `goal ==
    # option_allgemcups` check to the composed `gems_required_goal > 0`
    # condition. Behaviourally identical for what used to be reachable
    # (the old Choice's allgemcups value maps onto gems_required_goal ==
    # 5), and now correctly fires for any active Gems Required Goal
    # count, not just "all 5".
    _GEM_GOAL = world.options.gems_required_goal.value > 0
    _gems_locked: Dict[str, int] = {}
    _keys_locked: Dict[str, int] = {}
    _vmap = json.loads(
        pkgutil.get_data(__package__, "data/vanilla_mapping.json").decode("utf-8")
    )["ShuffleOptions"]

    # Gems: pin to gem-cup locations when shuffle_gems is OFF. When Gems
    # Required Goal is active with shuffle off, gemgoal() already placed
    # them (and place_locked_item on an already-filled location would
    # raise), so skip the placement here for that goal -- the pool
    # exclusion below still applies. Gems Required Goal + shuffle ON pins
    # nothing anywhere: the gems ride the pool (2026-07-15 ruling).
    if not world.options.shuffle_gems.value and not _GEM_GOAL:
        for _loc_name, _gem_name in _vmap["Gems"].items():
            _loc_name = replacement_trophy_location(
                resolved_custom_tracks(world), _loc_name)
            mw.get_location(_loc_name, player).place_locked_item(
                world.create_item(_gem_name)
            )
            _gems_locked[_gem_name] = _gems_locked.get(_gem_name, 0) + 1

    # Keys: pin to boss-race locations when shuffle_keys is OFF.
    if not world.options.shuffle_keys.value:
        for _loc_name, _key_name in _vmap["Boss Keys"].items():
            mw.get_location(_loc_name, player).place_locked_item(
                world.create_item(_key_name)
            )
            _keys_locked[_key_name] = _keys_locked.get(_key_name, 0) + 1

    # Gem cups (issue #50): pin the vanilla
    # Gem onto each of the 5 "<Colour> Gem Cup: Gem" checks when
    # include_gem_cups is OFF but shuffle_gems is ON. Same defect as the
    # arenas: the option only keeps the cup warp pads vanilla-gated
    # (Regions.py) -- the 5 cup locations stay unconditional in
    # data/world.json, so with the Gems shuffled they are live multiworld
    # slots and fill hid logic-required progression on them (measured 4 of a
    # 12-seed sample). Pinning restores the vanilla Gem there and takes the
    # slot out of the pool; the cups stay reachable in logic (their vanilla
    # has('<Colour> CTR Token', 4) gate persists), so nothing softlocks.
    #
    # The three sibling configs are already covered elsewhere and must NOT
    # double-pin (place_locked_item on a filled location raises):
    #   - shuffle_gems OFF, gems_required_goal == 0: _gems_locked block
    #     (above) pinned them.
    #   - shuffle_gems OFF, gems_required_goal > 0: gemgoal() pinned them.
    #   - shuffle_gems ON, gems_required_goal > 0: unreachable here. The
    #     goal Gems ride the pool, so pinning them onto opted-out cups
    #     would strand the goal; generate_early's
    #     resolve_shuffle_gems_off_when_gem_goal_excludes_cups (2026-09-21
    #     ruling) resolves shuffle_gems to OFF before create_items runs, so
    #     this config always arrives as the gemgoal()-pinned row above. It
    #     used to raise OptionError instead. The _GEM_GOAL guard below is
    #     the belt-and-suspenders either way.
    _cups_locked: Dict[str, int] = {}
    if not world.options.include_gem_cups.value \
            and world.options.shuffle_gems.value and not _GEM_GOAL:
        for _loc_name, _gem_name in _vmap["Gems"].items():
            _loc_name = replacement_trophy_location(
                resolved_custom_tracks(world), _loc_name)
            mw.get_location(_loc_name, player).place_locked_item(
                world.create_item(_gem_name)
            )
            _cups_locked[_gem_name] = _cups_locked.get(_gem_name, 0) + 1

    # Resolved once, before the pool loop reads it per item: how many copies
    # of each supply-spending wumpa name this seed creates. Empty dict when
    # the ladder is off, so the loop's lookup is a cheap miss.
    _wumpa_counts = wumpa_family.created_item_counts(world)

    # --- Create general item pool ---
    # When Gems Required Goal is active, gemgoal() LOCKS the 5 gems at the
    # gem-cup locations, so adding the same 5 gems from the item table again
    # makes them redundant progression items: the pool then exceeds the
    # available locations (gemgoal also consumes 5 cup locations) -> FillError
    # ("N more progression items than locations") and an item/location count
    # mismatch. Exclude the gems from the general pool for that goal (they
    # are the goal items, placed at the cups). Seeds without Gems Required
    # Goal active keep gems in the pool (Turbo Track's vanilla 5-gem gate
    # needs them findable) UNLESS shuffle_gems pinned them, in which case
    # _gems_locked subtracts them.
    _GEMS = {"Red Gem", "Green Gem", "Blue Gem", "Yellow Gem", "Purple Gem"}
    for item in load_item_table():
        # Gems Required Goal: exclude the gems from the general pool ONLY
        # when gemgoal() locked them onto their cups (shuffle_gems off) --
        # adding them again would overflow the pool (see the note above).
        # With shuffle_gems ON the gems stay in the pool: they are the goal
        # items, hidden wherever the fill puts them (2026-07-15 ruling).
        if _GEM_GOAL and not world.options.shuffle_gems.value \
                and item["name"] in _GEMS:
            continue
        count = item["count"]
        if (item["name"] == "Wumpa Fruit" and
                world.options.oxide_goal.value == OxideGoal.option_101_percent and
                world.options.oxide_1_optional.value == 2):
            count = max(0, count - 1)  # existing copy locked at Oxide 1
        if world.options.itemsanity.value and item["name"] in ITEM_NAMES:
            count = 1
        # Tizi Helper (#223): exactly one copy, only when the option is on.
        # Same shape as the itemsanity line above -- the entry ships count 0
        # in data/items.json and the option is what makes it real. It adds no
        # location, so it is a straight +1 against this seed's supply; being
        # here (before the #14/#15 comfort-pack trim and the character
        # supply check) is what lets a deliberately reduced seed free a
        # comfort slot for it instead of overflowing the pool.
        if item["name"] == TIZI_HELPER_ITEM:
            count = tizi_helper.created_item_count(world)
        # The starting-wumpa ladder (2026-08-10 ruling): up to ten copies
        # of ONE progressive name, per the #12/#13 convention. Like the
        # helper above it carries no location of its own, so every copy is
        # one otherwise-filler slot spent, and it sits here -- before the
        # shedding tiers -- so a reduced seed can free a comfort slot for it
        # rather than overflowing. The two wumpa BUNDLES are deliberately
        # NOT here: they are filler substitutes drawn from the filler budget
        # further down, so counting them as pool demand would double-count
        # them against the supply check.
        if item["name"] in _wumpa_counts:
            count = _wumpa_counts[item["name"]]
        # Turbo Grant (#224): same shape and the same supply reasoning as
        # the helper above -- one copy when the option is on, no location of
        # its own, and placed before the comfort-pack trim so a reduced seed
        # frees a comfort slot for it rather than overflowing the pool.
        if item["name"] == TURBO_GRANT_ITEM:
            count = turbo_grant.created_item_count(world)
        if int(world.options.lettersanity.value) in (2, 3) and item["name"] in lettersanity.ALL_ITEM_NAMES:
            track = item["name"].rsplit("(", 1)[1][:-1]
            letter = item["name"].split(" ", 2)[1]
            count = int(track in world.options._lettersanity_selected and
                        (int(world.options.lettersanity.value) == 3 or
                         letter in world.options._lettersanity_selected[track]))
        if item["name"] in _relic_locked:                         # slider-pinned relics
            count = max(0, count - _relic_locked[item["name"]])
        if item["name"] in _gems_locked:                          # gems pinned vanilla
            count = max(0, count - _gems_locked[item["name"]])
        if item["name"] in _keys_locked:                          # keys pinned vanilla
            count = max(0, count - _keys_locked[item["name"]])
        if item["name"] in _cups_locked:                          # gem cups pinned vanilla
            count = max(0, count - _cups_locked[item["name"]])
        if count > 0:
            for _ in range(count):
                pool.append(world.create_item(item["name"]))

    # Sparse custom letter items follow certified slot selection, not the
    # positional retail item table. Include before capacity/overflow checks.
    pool.extend(world.create_item(name) for name in
                CUSTOM_LETTERSANITY_CLASS.created_item_names(world.options))
    # A track with a named block pools its block's letter items instead (#133).
    from .custom_track_ids import created_named_item_names
    pool.extend(world.create_item(name) for name in
                created_named_item_names(world.options))
    # Cortex Vortex's letter items live outside the positional table, like
    # the custom ones above. Empty with the option off.
    pool.extend(world.create_item(name) for name in
                cortex_vortex_track.created_letter_item_names(world.options))
    # Spoiler Items (#459): the one or two reveal items. Like Tizi Helper they
    # add no location, so they go in before overflow shedding, which may then
    # drop filler or the comfort pack to make room. Empty with the option off.
    _spoiler_names = spoiler_items.created_item_names(world)
    pool.extend(world.create_item(name) for name in _spoiler_names)

    # --- Character unlocks (issues #54 / #209, R4). ALWAYS ON: the
    # character phase is core 0.2.0 content, not a toggle, so every seed
    # puts the 15 racers you did not start as into the pool and pushes the
    # one you did start as as precollected. They add ZERO locations, so
    # they are a straight +15 against this seed's supply -- which is why
    # they go in BEFORE the comfort-pack trim below rather than after it,
    # so a deliberately reduced seed frees the five optional #14/#15
    # comfort items for them instead of overflowing.
    #
    # Classification is per-seed (R17) and lives in create_item: progression
    # when racer-locked pads are on, useful when they are off. Remove
    # Playable Oxide (#426) leaves Oxide's item out (14 racers); the filler
    # top-up at the end of this method fills the freed slot.
    _start_character = world.ctr_starting_character
    mw.push_precollected(world.create_item(
        characters.unlock_item_name(_start_character)))
    for _unlock_name in characters.created_unlock_names(world):
        pool.append(world.create_item(_unlock_name))

    # --- Overflow shedding (maintainer ruling, 2026-08-18): FILLER first, then
    # the comfort pack, then refuse. The tiers, the reasoning and what is
    # never shed all live in item_supply.shed_overflow, which is a pure
    # function so every tier is reachable from a synthetic pool instead of
    # only from a seed whose options happen to land on the right overflow.
    # That testability is the point: the all-or-nothing behaviour this
    # replaced survived because reaching it needed roughly a 1-in-500 seed.
    #
    # A returned pool may be SMALLER than `unfilled` (tier 2 drops the pack
    # whole), which the filler top-up at the end of this method closes, and
    # it may still be LARGER, which the general capacity guard below
    # refuses.
    unfilled = len(mw.get_unfilled_locations(world.player))
    shedding_supply = unfilled
    if (world.options.oxide_goal.value == OxideGoal.option_101_percent and
            world.options.oxide_1_optional.value == 2):
        # The original generic filler is now locked at First. Excluded
        # locations still need their own filler in the unfilled pool.
        # Reserve those copies before overflow shedding so the comfort
        # pack, not mandatory items or that reserve, yields tight slots.
        floor = estimated_filler_reserve(world)
        have = sum(item.classification == ItemClassification.filler for item in pool)
        pool += [world.create_item("Wumpa Fruit") for _ in range(max(0, floor-have))]
        # Capability packs are appended below. Account for them while
        # deciding whether the optional comfort pack still fits.
        shedding_supply -= sum(progressive_capability.created_item_counts(world).values())
    pool = item_supply.shed_overflow(
        pool, shedding_supply, SURFACE_ITEM_NAMES,
        filler_floor=estimated_filler_reserve(world))

    if int(world.options.lettersanity.value) == 3 and len(pool) > unfilled:
        raise OptionError(
            f"CTR: Lettersanity 'items_only' needs 48 spare filler slots, but this "
            f"option combination has only {max(0, unfilled - (len(pool) - 48))}. "
            "Enable more location checks or reduce other item packs.")

    # --- Progressive Boost / Progressive Stats item packs (issues #12,
    # #13/#252). Classification is resolved per seed in create_item from
    # the live rule readers. Empty dict when
    # both packs are off, so this is a no-op (byte-identical to a
    # pre-#12/#13 seed, no RNG draw taken) in the default configuration.
    # Runs AFTER the #14/#15 comfort-pack trim above so a tight seed's
    # freed slots (from omitting the comfort pack) are available to these
    # items too -- `unfilled` is the same live count either block reads,
    # `len(pool)` reflects whatever the trim above already did.
    _capability_counts = progressive_capability.created_item_counts(world)
    if _capability_counts:
        _capability_supply = unfilled - len(pool)
        progressive_capability.raise_if_capability_items_exceed_location_supply(
            world, available_supply=_capability_supply)
        for _cap_name, _cap_count in _capability_counts.items():
            for _ in range(_cap_count):
                pool.append(world.create_item(_cap_name))

    # The character-unlock capacity check (issues #54/#209, R4). It runs
    # AFTER every option-specific item family -- character unlocks, the
    # shedding tiers, itemsanity weapons, and the progressive packs above --
    # is in the pool, so `len(pool)` is the COMPLETE current pool and
    # `unfilled` is the live post-creation location count (never a predicted
    # constant). Computed against the supply that would remain WITHOUT the
    # unlocks, so the message is honest about what is missing rather than
    # blaming whichever family happened to be appended last. No-op in
    # all-unlocked mode and on every seed that fits.
    #
    # It runs FIRST of the two capacity checks deliberately: when the
    # unlocks are what does not fit, its message says so specifically, which
    # is more useful than the general one below.
    # Spoiler Items (#459) first: an enabled reveal item is never silently
    # omitted, and when it alone tips the pool over, the message names it.
    spoiler_items.raise_if_items_do_not_fit(len(pool), unfilled, _spoiler_names)
    characters.raise_if_unlocks_exceed_location_supply(
        world, available_supply=unfilled - (
            len(pool) - len(characters.created_unlock_names(world))))

    # THE general net-capacity check (2026-08-18). Every earlier guard is
    # per-family and therefore silent outside its own feature: the
    # lettersanity one covers only `items_only`, the capability one runs
    # only with a pack enabled, and the character one is a no-op when the
    # unlocks are off. A seed with all three inapplicable could reach fill
    # with more items than locations and die inside Archipelago's filler
    # stage with a message naming none of this -- which is exactly what the
    # 2026-08-18 mismatch did. This is the backstop that makes the next
    # no-location item family fail loudly at option-validation time instead
    # of one seed in five hundred later.
    #
    # It is placed after the shedding tiers ON PURPOSE: shedding is the
    # world's own attempt to fit, and only a seed that survives both tiers
    # still over is genuinely unsatisfiable.
    if len(pool) > unfilled:
        raise OptionError(
            f"CTR: this option combination creates {len(pool) - unfilled} more "
            f"item(s) than it has locations to hold them ({len(pool)} items, "
            f"{unfilled} locations). Enable more checks -- item boxes, itemsanity, "
            "podium rungs or lettersanity locations -- or turn off one of the "
            "options that add an item without adding a location.")

    mw.itempool += pool
    # Size filler off the UNFILLED locations, i.e. total minus the locations
    # already locked above (the goal-tracking companion events _install_goal
    # locks, and for the gem-cup goal the 5 locked gems). Using the static
    # get_total_locations over-counted by the
    # number of locked locations -> 1 (or 5) excess filler items -> the
    # item/location count mismatch the fuzzer flags. Clamp at 0 for safety.
    #
    # Count against THIS player's pool, not the global mw.itempool: in a
    # multiworld, mw.itempool already holds every earlier-processed world's
    # items here, so the old `unfilled - len(mw.itempool)` went negative and
    # silently skipped the top-up for any CTR world whose create_items did not
    # run first -> that player ended 1 item short of their locations ->
    # deterministic "Player X had 1 more locations than items" + FillError on
    # every multi-CTR generation with a filler-needing config. Solo unchanged
    # (there len(pool) == len(mw.itempool)).
    n_filler = max(0, unfilled - len(pool))
    # Trap fill: replace trap_fill_percentage% of the filler slots with traps,
    # drawn against the player's trap_weights (#280 -- the uniform v1 draw is
    # gone). Traps are non-progression, so this never changes reachability at
    # any value. trap_fill_percentage 0 IS GENERATION-NEUTRAL BY
    # CONSTRUCTION: the else branch is byte-identical to the old Wumpa-only
    # fill and no world.random draw is taken, so such a seed's spoiler +
    # slot_data are unchanged -- which is also why an all-zero weight table
    # is only an error when the fill is above 0.
    trap_pct = world.options.trap_fill_percentage.value
    if trap_pct > 0 and n_filler > 0:
        n_traps = (n_filler * trap_pct) // 100
        for trap_name in traps.draw_trap_names(world, n_traps):
            mw.itempool.append(world.create_item(trap_name))
        mw.itempool += [world.create_item(wumpa_family.draw_filler_name(world))
                        for _ in range(n_filler - n_traps)]
    else:
        mw.itempool += [world.create_item(wumpa_family.draw_filler_name(world))
                        for _ in range(n_filler)]

    # NOTE: an earlier density-adaptive force-collapse was removed -- CTR's pool
    # is ~98% progression in EVERY config (only ~1 filler item), so a density
    # signal cannot distinguish a tight seed from a normal one and would collapse
    # two-stage on virtually all seeds (defeating "two-stage is the DEFAULT
    # experience"). Solvability is instead held by the sphere-search invariant,
    # the per-pad relax-to-tier-1 fallback + baseline collapse roll, the stage
    # count ceilings, the slider-aware relic filter, and the min-2 bootstrap
    # breadth -- all proven to fill 0/5000 randomized two-stage-active configs
    # while keeping real, distinct tier-2 gates on the great majority of pads.
