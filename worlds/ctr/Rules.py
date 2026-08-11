import logging
from BaseClasses import CollectionState

from .gem_cup_legs import resolved_gem_cup_legs, track_to_cups


def make_rule(expr_text: str, player: int):
    """
    Converts simple logic like:
        has('Key', 2) and has('Progressive Relic', 10)
    into a combined rule lambda.
    """
    expr_text = expr_text.strip()

    if not expr_text or expr_text.lower() in ("true", "always"):
        return lambda state: True

    parts = [p.strip() for p in expr_text.split("and")]

    def rule(state: CollectionState):
        for part in parts:
            if not part.startswith("has("):
                logging.warning(f"[CTR Rules] Unsupported rule segment '{part}' in '{expr_text}'")
                return False

            # Parse has('Item', N)
            inner = part[4:-1]  # remove has( ... )
            args = [x.strip().strip("'\"") for x in inner.split(",")]

            if not args:
                logging.warning(f"[CTR Rules] Empty has() in '{expr_text}'")
                return False

            item = args[0]
            count = int(args[1]) if len(args) > 1 else 1

            if not state.has(item, player, count):
                return False
        return True

    return rule


def set_rules(world):
    """
    Applies JSON-defined access rules to entrances and locations,
    and enforces CTR-specific Trophy prerequisites.
    """
    player = world.player
    mw = world.multiworld

    for region in mw.get_regions(player):
        for ent in region.exits:
            rule_text = getattr(ent, "access_rule_text", "True")
            ent.access_rule = make_rule(rule_text, player)

        for loc in region.locations:
            rule_text = getattr(loc, "logic_text", "True")
            loc.access_rule = make_rule(rule_text, player)

    add_time_trial_and_ctr_requirements(world, player)

    # Native-randomization (Phase-2 MVP): install the resolved per-pad unlock
    # requirements and boss-garage gates LAST so they win over the JSON text
    # rules already applied above.
    add_warp_pad_unlock_rules(world, player)
    # Vanilla warp-pad mode (issue #80): the per-pad native trophy floor. In
    # randomized modes add_warp_pad_unlock_rules already installed the sphere-search
    # requirements (and world.warp_pad_unlock is empty in vanilla), so this ANDs the
    # vanilla floor on exactly one mode. Same slot as add_warp_pad_unlock_rules.
    if world.options.warppad_unlock_requirements.value == 0:
        add_vanilla_floor_rules(world, player)
    add_boss_garage_rules(world, player)
    add_podium_placement_rules(world, player)
    add_itemsanity_rules(world, player)
    add_item_box_rules(world, player)


def add_item_box_rules(world, player):
    """Per-slot item-term rules for the created #109 box locations.

    The `shortcut_knowledge` tier is a CREATION decision (a slot above the
    seed's tier is never created), so the only state terms here are item
    terms, and each term is vacuous while the option that creates its items
    is off (seating spec 2.2 -- a rule requiring an item that cannot exist
    makes the seed unfillable, the #145 FillError class):

    - `Progressive Boost >= n` binds only when `progressive_boost` is
      randomized (with the pack off every kart has vanilla boost).
    - "each stat chain >= 1" (the hard-tier general rule) binds only when
      `progressive_stats` is randomized.
    - The Tiger Temple door slot additionally needs one of the seven ledger
      door-opener weapons, but only when `itemsanity` is on -- with it off,
      weapon rolls are not modelled and any roll can open the door.

    Like the itemsanity rules, every item term here reads items that
    create_item upgrades to `progression` in exactly these seeds; a term on a
    `useful` item would be permanently unsatisfiable in logic.
    """
    from .item_boxes import (BOX_RULES, ITEM_BOX_CLASS,
                             TIGER_TEMPLE_DOOR_OPENERS)
    from .progressive_capability import STAT_CHAINS

    created = set(ITEM_BOX_CLASS.created_location_names(world.options))
    if not created:
        return

    boost_on = bool(world.options.progressive_boost.value)
    stats_on = bool(world.options.progressive_stats.value)
    itemsanity_on = bool(world.options.itemsanity.value)

    for (track, slot), (boost_min, needs_stats) in BOX_RULES.items():
        name = ITEM_BOX_CLASS.location_name(track, slot)
        if name not in created:
            continue
        need_boost = boost_min if boost_on else 0
        need_stats = needs_stats and stats_on
        door = (TIGER_TEMPLE_DOOR_OPENERS
                if itemsanity_on and (track, slot) == ("Tiger Temple", 5)
                else None)
        if not need_boost and not need_stats and door is None:
            continue

        def _rule(state, p=player, need_boost=need_boost,
                  need_stats=need_stats, door=door):
            if need_boost and state.count("Progressive Boost", p) < need_boost:
                return False
            if need_stats and not all(state.has(chain, p)
                                      for chain in STAT_CHAINS):
                return False
            if door is not None and not state.has_any(door, p):
                return False
            return True

        world.multiworld.get_location(name, player).access_rule = _rule


def add_itemsanity_rules(world, player):
    """Apply the received-weapon rules for Itemsanity's global checks.

    ONLY Turbo additionally requires boost capability, and only when
    Progressive Boost is randomized (#145 Decision 2 ruling, 2026-08-10) --
    every other weapon fires regardless of boost tier, so attaching the term
    to all eleven was a bug (it produced FillErrors once the pool held more
    useful items than non-itemsanity slots).  With the pack off, vanilla
    boost is available from the start, so the term is deliberately vacuous
    instead of requiring a nonexistent Progressive Boost item.

    The `state.has("Progressive Boost")` term is only meaningful because
    `ctrAPWorld.create_item` upgrades the boost chain to `progression` in
    exactly the seeds where this rule reads it; logic state never tracks
    `useful` items, so without that upgrade the Turbo checks would be
    permanently out of logic.
    """
    from .itemsanity import ITEMSANITY_CLASS, WEAPONS

    if not ITEMSANITY_CLASS.is_enabled(world.options):
        return

    boost_randomized = bool(world.options.progressive_boost.value)
    for weapon in WEAPONS:
        need_boost = boost_randomized and weapon == "Turbo"

        def _rule(state, weapon=weapon, p=player, need_boost=need_boost):
            return (state.has(weapon, p)
                    and (not need_boost or state.has("Progressive Boost", p)))

        for juiced in (False, True):
            world.multiworld.get_location(
                ITEMSANITY_CLASS.location_name(weapon, juiced), player
            ).access_rule = _rule


# ITEM name resolver for a randomized requirement type code (see §0 contract).
# colour is 0..4 = R,G,B,Y,P for token/gem types; 0..2 = Sapphire,Gold,Platinum for
# the type-4 relic tier (schema_version 4). Relic tiers are INDEPENDENT items with no
# downward hierarchy, so type 4 must decode the concrete tier -- hard-coding "Sapphire
# Relic" (the pre-schema-4 bug) silently rewrote every gold/platinum gate to sapphire.
# The call site passes `colour if colour >= 0 else 0`, so a legacy colour -1 still
# decodes to Sapphire, preserving pre-4 behaviour for any old {type:4,colour:-1} req.
ITEM_BY_TYPE = {
    1: lambda c: "Trophy",
    2: lambda c: "Key",
    3: lambda c: ["Red", "Green", "Blue", "Yellow", "Purple"][c] + " CTR Token",
    4: lambda c: ["Sapphire", "Gold", "Platinum"][c] + " Relic",
    5: lambda c: ["Red", "Green", "Blue", "Yellow", "Purple"][c] + " Gem",
}

# Aggregate "any N of a type" item lists, for requirement_specificity = any_of.
# A type-6/7/8 gate (or an "AnyCtrToken"/"AnyRelic"/"AnyGem" stage-2 tuple) is met
# when the SUM of state.count across the whole type reaches N -- genuine any-of
# semantics, not a single concrete colour/tier.
_AGG_TOKENS = ["Red CTR Token", "Green CTR Token", "Blue CTR Token",
               "Yellow CTR Token", "Purple CTR Token"]
_AGG_RELICS = ["Sapphire Relic", "Gold Relic", "Platinum Relic"]
_AGG_GEMS = ["Red Gem", "Green Gem", "Blue Gem", "Yellow Gem", "Purple Gem"]

# Aggregate item lists by slot_data type code (6/7/8) and by Any* item name.
AGG_BY_TYPE = {6: _AGG_TOKENS, 7: _AGG_RELICS, 8: _AGG_GEMS}
AGG_BY_NAME = {"AnyCtrToken": _AGG_TOKENS, "AnyRelic": _AGG_RELICS,
               "AnyGem": _AGG_GEMS}


def _agg_has(state, names, player, count):
    """True iff the player owns at least `count` items summed across `names`."""
    return sum(state.count(n, player) for n in names) >= count


def _scoped_agg_names(world, names):
    """Scope an aggregate item list for AP reachability (issue #118).

    When include_battle_arenas is OFF the arenas are out of the seed: the four
    Crystal Bonus Round checks are vanilla-pinned with their own Purple CTR Tokens,
    so every Purple is locked behind arena play. If AP logic counted those Purples
    toward an "any N tokens" gate, fill/playthrough could route a required item
    behind a gate only arena play satisfies -- exactly what the option promises it
    will not. So drop Purple CTR Token from the token aggregate here, mirroring the
    sphere-search exclusion in warp_pad_logic._run_sphere_search_once (which also
    sized N over the non-Purple colours only, so the gate stays satisfiable).

    Only the token aggregate is affected; relic/gem lists pass through unchanged.
    This makes apworld logic STRICTER than native, which still counts received
    Purples toward its gate sums -- that asymmetry only ever makes a seed easier
    than AP logic assumes, never unbeatable, so the direction of safety holds.
    """
    if not bool(world.options.include_battle_arenas.value):
        return [n for n in names if n != "Purple CTR Token"]
    return names


def add_warp_pad_unlock_rules(world, player):
    """Install the per-seed sphere-search requirements on the pad exits.

    world.warp_pad_unlock is {pad_exit_name -> {type,count,colour}} produced by
    warp_pad_logic.run_sphere_search; empty in vanilla mode. type 0 = free pad
    (keep the JSON text rule -> N. Sanity Beach starters chosen FREE stay open).

    Icebound's real algorithm randomizes the N. Sanity Beach starters too: any
    starter NOT in the free subset now arrives here with a real requirement. The
    free subset guarantees sphere 0 is non-empty, so the seed stays solvable.

    SOLVABILITY: the requirement is ANDed with the pad's EXISTING vanilla access
    rule (the Key-gated hub backbone), not a replacement. The sphere-search
    assigned only requirements that are satisfiable when the pad is first
    reachable, so the AND keeps a reachable item-placement frontier for fill.
    Any* requirements were resolved to a concrete owned colour upstream, so the
    {type,colour} here always names a single concrete item.
    """
    mw = world.multiworld
    for pad_name, req in getattr(world, "warp_pad_unlock", {}).items():
        t, count, colour = req["type"], req["count"], req["colour"]
        if t == 0:
            continue  # native-fixed pad (vanilla mode) / not randomized; keep text rule
        ent = mw.get_entrance(pad_name, player)
        base_rule = ent.access_rule  # vanilla Key-gate already applied above
        if t in AGG_BY_TYPE:
            # any_of aggregate: gate is "any N of this type" summed across colours/tiers.
            names = _scoped_agg_names(world, AGG_BY_TYPE[t])
            ent.access_rule = (
                lambda state, ns=names, n=count, p=player, base=base_rule:
                base(state) and _agg_has(state, ns, p, n)
            )
        else:
            item = ITEM_BY_TYPE[t](colour if colour >= 0 else 0)
            ent.access_rule = (
                lambda state, i=item, n=count, p=player, base=base_rule:
                base(state) and state.has(i, p, n)
            )


def add_vanilla_floor_rules(world, player):
    """Vanilla warp-pad mode (warppad_unlock_requirements = vanilla, issue #80):
    AND each race pad's native trophy floor onto its ENTRANCE rule.

    The floor is a property of the PHYSICAL pad -- native gates the pad LOAD by
    physLevelID against metaDataLEV[].numTrophiesToOpen (AH_WarpPad.c:836/1923),
    NOT the race -- so it belongs on the pad exit, which Regions keeps in its
    physical hub and keeps physical-pad-keyed even under destination shuffle
    (race<->race per_category in this mode). Flooring the entrance rather than the
    Trophy Race location thus reproduces native's physical-pad keying for free and
    makes Regions' old location-floor re-key hack unnecessary (removed).

    Floors are read from data/warp_pad_ids.json ("vanilla_trophies"), the single
    source transcribed from the native table; NEVER retyped here. A floor of 0
    (Crash Cove / Roo's Tubes) adds no rule, so the two vanilla starter pads stay
    open from an empty inventory -- the bootstrap that lets the first trophies be
    earned. Only "kind": "race" pads carry a floor (arenas gate on hub keys, trials
    on relics/gems).

    Base-rule capture: the floor is ANDed onto the entrance's existing hub-Key rule
    (the pattern of add_warp_pad_unlock_rules), never replacing it.
    """
    mw = world.multiworld
    for pad_name, meta in getattr(world, "warp_pad_ids", {}).items():
        if meta.get("kind") != "race":
            continue
        floor = meta.get("vanilla_trophies", 0)
        if floor <= 0:
            continue  # floor-0 pads (Crash Cove / Roo's Tubes): stay open, bootstrap
        ent = mw.get_entrance(pad_name, player)
        base_rule = ent.access_rule  # vanilla hub-Key gate already applied above
        ent.access_rule = (
            lambda state, n=floor, p=player, base=base_rule:
            base(state) and state.has("Trophy", p, n)
        )


# Garage-door exit name -> trophy threshold (vanilla 4/8/12/16). Oxide left as
# its has('Key', 4) text rule.
HUB_BOSS = {
    "Ripper Roo Garage Door": 4,
    "Papu Papu Garage Door": 8,
    "Komodo Joe Garage Door": 12,
    "Pinstripe Garage Door": 16,
}


def add_boss_garage_rules(world, player):
    """Install boss-garage access rules from the resolved flat requirements.

    MVP: all three boss-garage modes (Original4Tracks / SameHubTracks / Trophies)
    map to the SAME trophy-count gates (4/8/12/16) in logic. AP-core therefore
    reasons about an identical, solvable topology regardless of the chosen mode,
    so the three modes share one fill behaviour today (this is why all three fuzz
    green with the same solvability).

    The real bossgarage_mode int plus the per-boss 'tracks' LevelID lists for modes
    0/1 are still emitted in slot_data (Regions._resolve_boss_reqs ->
    boss_garage_req). The full Original4Tracks / SameHubTracks experience -- gating
    on which specific tracks were won rather than on a flat trophy count -- is
    deferred to native, where it needs pad-specific win-bit tracking that the gate
    sites in AH_Garage.c do not have yet (documented in
    native_patches/6_bossmodes.patch). When that native support lands, the trophy
    gate here can stay as the logical proxy (winning a track yields a trophy, so the
    trophy count is a sound lower bound on solvability), or be tightened to a
    can_reach over the four track Trophy Races -- no slot_data change required.
    """
    mw = world.multiworld
    for door, thr in HUB_BOSS.items():
        ent = mw.get_entrance(door, player)
        ent.access_rule = (
            lambda s, n=thr, p=player: s.has("Trophy", p, n)
        )
    # N. Oxide Garage Door keeps its has('Key', 4) text rule.


def add_podium_placement_rules(world, player):
    """Podium placement rungs (position-rung rework, shipped 0.1.x) are reachable
    exactly when their destination track is RACEABLE.

    They fire native-side from the placement listener, and a win satisfies every
    rung (the ladder), so "the track is raceable" is both necessary (you must be
    able to run it) and sufficient (a winnable race yields all rungs) -- the same
    assumption the shipped podium checks used. A track is raceable when EITHER:

    * its own Trophy Race LOCATION is reachable -- delegating here inherits every
      warp-pad mode for free (vanilla floor, randomized floor-strip,
      destination-shuffle rekey all already live on that location's rule); OR
    * one of the Gem Cups that runs this track as a LEG is reachable -- a cup leg
      is a real track load, so finishing a leg fires that track's rungs (design
      decision 3). Modelled as an OR on the RUNG rule (not a cup->track region
      entrance): a cup->track entrance would also expose that track's Time Trials
      / CTR Token Challenge / Trophy Race, which a cup leg does NOT earn, and
      would over-state their reachability (golden-rule violation). The OR touches
      only the rungs, which is exactly what a leg finish earns.

    JOINT PODIUM REGION (issue #86). The rungs do NOT live in the track region;
    Regions.create_regions parents them to a dead-end "<track>: Podium" region
    with rule-True entrances FROM the track region and FROM each legging cup. That
    is what keeps this OR alive: AP-core ANDs a Location's rule with its parent
    region's reachability, so a cup-only rung parented to the track region (its
    pad shut) would be ANDed out of logic. The podium region holds only rungs and
    has no exits, so the cup entrance still exposes nothing but the rungs -- the
    golden rule above is preserved by the region's dead-end shape, not just by the
    rule. can_reach = (trackRegion OR cup) AND (trophyLoc OR cup) = (trophyLoc OR
    cup), since trophyLoc reachability implies trackRegion. This rule is unchanged
    by the fix.

    No placement is ever logically required, so accessibility:full stays
    satisfiable whenever the trophy race is."""
    o = world.options
    from .podium import TROPHY_TRACKS, created_rung_keys_from_options, location_name
    rung_keys = created_rung_keys_from_options(o)
    if not rung_keys:
        return
    mw = world.multiworld
    all_names = {loc.name for loc in mw.get_locations(player)}
    all_regions = {r.name for r in mw.get_regions(player)}
    # The seed's resolved leg map (issue #166), stashed by create_regions:
    # vanilla table, or the randomized/UT-pinned map. Fails loudly rather
    # than silently falling back to vanilla if create_regions never ran --
    # a wrong-but-plausible seed is worse than a crash (N3, Opus review).
    track_cups = track_to_cups(resolved_gem_cup_legs(world))
    for track in TROPHY_TRACKS:
        trophy_name = f"{track}: Trophy Race"
        if trophy_name not in all_names:
            continue
        # Cups that leg this track AND actually exist as regions this seed.
        cups = [c for c in track_cups.get(track, []) if c in all_regions]
        for rung_key in rung_keys:
            name = location_name(track, rung_key)
            if name not in all_names:
                continue
            loc = mw.get_location(name, player)
            if cups:
                loc.access_rule = (
                    lambda state, t=trophy_name, cs=tuple(cups), p=player:
                    state.can_reach(t, "Location", p)
                    or any(state.can_reach(c, "Region", p) for c in cs)
                )
            else:
                loc.access_rule = (
                    lambda state, t=trophy_name, p=player:
                    state.can_reach(t, "Location", p)
                )


def add_time_trial_and_ctr_requirements(world, player):
    """
    Lock Time Trials and CTR Challenges until their track's Trophy Race is completed,
    except for bonus tracks like Slide Coliseum and Turbo Track.

    TWO-STAGE: for the 16 trophy pads in randomized mode, the track's CTR Token
    Challenge + 3 relic Time Trials carry a STAGE-2 requirement ANDed on top of the
    Trophy-Race-reachable rule (stage 1). world.warp_pad_unlock_stage2_concrete is
    keyed by DESTINATION track (== the location's own track prefix, since these
    locations live in the destination region under shuffle) -> {(item,count)}.
    Empty in vanilla mode / for pads with no stage 2 -> the rule is the plain
    can_reach(Trophy Race), exactly as before.
    """
    mw = world.multiworld
    all_location_names = {loc.name for loc in mw.get_locations(player)}
    # Density-adaptive collapse (set in create_items): on a maximally tight seed,
    # drop EVERY stage-2 gate so the relic/token locations are gated only by their
    # Trophy Race (deliberate per-seed collapse). Keeps the seed fillable
    # without ever pinning rewards or overriding the sliders.
    if getattr(world, "_ctr_force_collapse_stage2", False):
        stage2 = {}
    else:
        stage2 = getattr(world, "warp_pad_unlock_stage2_concrete", {})

    for loc in mw.get_locations(player):
        name = loc.name

        if not (name.endswith("Time Trial") or name.endswith("CTR Token Challenge")):
            continue

        track_prefix = name.split(":")[0].strip()
        trophy_name = f"{track_prefix}: Trophy Race"

        if trophy_name not in all_location_names:
            logging.debug(
                f"[CTR Rules] Skipping prerequisite for {name} (no Trophy Race found)")
            continue

        s2 = stage2.get(track_prefix)
        if s2 is not None:
            s2_item, s2_count = s2

            if s2_item in AGG_BY_NAME:
                # any_of aggregate stage-2 gate: "any N of this type", summed.
                def rule(state: CollectionState, t=trophy_name, p=player,
                         ns=_scoped_agg_names(world, AGG_BY_NAME[s2_item]), n=s2_count):
                    return state.can_reach(t, "Location", p) and _agg_has(state, ns, p, n)
            else:
                def rule(state: CollectionState, t=trophy_name, p=player,
                         i=s2_item, n=s2_count):
                    return state.can_reach(t, "Location", p) and state.has(i, p, n)

            logging.debug(
                f"[CTR Rules] {name}: Trophy({trophy_name}) AND stage2 has({s2_item},{s2_count})")
        else:
            def rule(state: CollectionState, t=trophy_name, p=player):
                return state.can_reach(t, "Location", p)

            logging.debug(
                f"[CTR Rules] Added Trophy prerequisite: {name} requires {trophy_name}")

        loc.access_rule = rule
