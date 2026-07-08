import logging
from BaseClasses import CollectionState


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
    add_boss_garage_rules(world, player)
    add_podium_placement_rules(world, player)


# ITEM name resolver for a randomized requirement type code (see §0 contract).
# colour is 0..4 = R,G,B,Y,P for token/gem types.
ITEM_BY_TYPE = {
    1: lambda c: "Trophy",
    2: lambda c: "Key",
    3: lambda c: ["Red", "Green", "Blue", "Yellow", "Purple"][c] + " CTR Token",
    4: lambda c: "Sapphire Relic",
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
            names = AGG_BY_TYPE[t]
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
    """Podium placement checks (feat/podium-checks) are reachable exactly when
    their track's Trophy Race is.

    They fire native-side from the placement listener regardless of finishing
    position, and finishing 1st satisfies every rung, so a plain
    can_reach(Trophy Race) rule is both necessary (you must be able to run the
    race) and sufficient (a winnable race yields all rungs). Delegating to the
    Trophy Race LOCATION's reachability inherits every warp-pad mode for free --
    vanilla trophy floor, randomized floor-strip, and destination-shuffle rekey
    all already live on that location's rule. No placement is ever logically
    required, so accessibility:full stays satisfiable whenever the trophy race is.
    """
    o = world.options
    if not bool(o.podium_placement_checks.value):
        return
    from .podium import TROPHY_TRACKS, enabled_rung_keys, location_name
    mw = world.multiworld
    all_names = {loc.name for loc in mw.get_locations(player)}
    rung_keys = enabled_rung_keys(bool(o.podium_any_position_rung.value))
    for track in TROPHY_TRACKS:
        trophy_name = f"{track}: Trophy Race"
        if trophy_name not in all_names:
            continue
        for rung_key in rung_keys:
            name = location_name(track, rung_key)
            if name not in all_names:
                continue
            loc = mw.get_location(name, player)
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
                         ns=AGG_BY_NAME[s2_item], n=s2_count):
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
