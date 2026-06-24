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


# ITEM name resolver for a randomized requirement type code (see §0 contract).
# colour is 0..4 = R,G,B,Y,P for token/gem types.
ITEM_BY_TYPE = {
    1: lambda c: "Trophy",
    2: lambda c: "Key",
    3: lambda c: ["Red", "Green", "Blue", "Yellow", "Purple"][c] + " CTR Token",
    4: lambda c: "Sapphire Relic",
    5: lambda c: ["Red", "Green", "Blue", "Yellow", "Purple"][c] + " Gem",
}


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
        item = ITEM_BY_TYPE[t](colour if colour >= 0 else 0)
        base_rule = ent.access_rule  # vanilla Key-gate already applied above
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

    MVP: all boss-garage modes map to trophy-count gates (4/8/12/16). The real
    bossgarage_mode int is still emitted in slot_data for future native use.
    """
    mw = world.multiworld
    for door, thr in HUB_BOSS.items():
        ent = mw.get_entrance(door, player)
        ent.access_rule = (
            lambda s, n=thr, p=player: s.has("Trophy", p, n)
        )
    # N. Oxide Garage Door keeps its has('Key', 4) text rule.


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
