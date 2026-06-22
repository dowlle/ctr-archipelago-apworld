import json
import pkgutil
from BaseClasses import Region, Entrance, EntranceType
from .Locations import create_location
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from . import ctrAPWorld


# ---------------------------------------------------------------------------
# Native-randomization support (Phase-2 MVP).
# Shared slot_data contract: apworld EMITS resolved values, native PARSES.
# See spec "2026-06-22 -- Spec -- Randomized Playthrough MVP (Phase 2-MVP)".
# ---------------------------------------------------------------------------

# Requirement-type code -> live item-pool ceiling (the §0 "available items" table).
# Randomized counts MUST NOT exceed these or the seed becomes unsolvable.
#   1 trophies (16) / 2 keys (4) / 3 tokens-per-colour (4) / 4 sapphire (18) / 5 gems-per-colour (1)
REQ_AVAIL = {1: 16, 2: 4, 3: 4, 4: 18, 5: 1}

# Boss-garage trophy thresholds (vanilla 4/8/12/16). Oxide stays keys.
BOSS_TROPHY = {"ripper_roo": 4, "papu_papu": 8, "komodo_joe": 12, "pinstripe": 16}


def _load_warp_pad_ids():
    """pad-exit-name -> {level_id, kind} from data/warp_pad_ids.json."""
    return json.loads(
        pkgutil.get_data(__package__, "data/warp_pad_ids.json").decode("utf-8")
    )["pads"]


def _shuffleable_pad_names(world, pad_ids):
    """Group-1 pad exits eligible for unlock-requirement randomization.

    Race pads always qualify. Crystal (battle-arena) pads qualify only when
    include_battle_arenas is set. Gem cups (kind 'cup') and the bonus trial
    pads (Slide/Turbo, kind 'trial') stay native-fixed -> they emit type:0 and
    are NEVER randomized here.

    SOLVABILITY BACKBONE: the four always-open N. Sanity Beach starter race
    pads (bootstrap=True) are EXCLUDED. They must stay reachable from an empty
    inventory so the player can win their first trophies; randomizing them risks
    a circular deadlock (need trophies to open the only trophy sources). They
    emit type:0 (native vanilla / always-open) in slot_data.
    """
    inc_arenas = bool(world.options.include_battle_arenas.value)
    names = []
    for pad_name, meta in pad_ids.items():
        if meta.get("bootstrap"):
            continue  # solvability backbone, never randomized
        kind = meta["kind"]
        if kind == "race":
            names.append(pad_name)
        elif kind == "crystal" and inc_arenas:
            names.append(pad_name)
        # cup / trial -> fixed, never randomized
    return names


def _random_pad_req(world, mode):
    """Draw a single (type, count, colour) within solvable bounds.

    mode 1 = random; mode 2 = random_without_4_keys.
    count <= REQ_AVAIL[type] guarantees the requirement is satisfiable; AP's
    fill_restrictive then validates the whole seed and reseeds on FillError.
    """
    choices = [1, 3, 4, 5] if mode == 2 else [1, 2, 3, 4, 5]
    t = world.random.choice(choices)
    colour = world.random.randint(0, 4) if t in (3, 5) else -1
    count = world.random.randint(1, REQ_AVAIL[t])
    if mode == 2 and t == 2 and count == 4:  # belt-and-suspenders: never a 4-key wall
        count = 3
    return {"type": t, "count": count, "colour": colour}


def _resolve_boss_reqs(boss_mode):
    """Resolve all 3 boss-garage modes to flat {type,count} server-side.

    MVP: modes 0/1/2 all collapse to trophy-count gates (4/8/12/16). The real
    bossgarage_mode int still ships in ctr_options so a future native build can
    branch; today native enforces these flat counts. Oxide = 4 keys, fixed.
    """
    req = {b: {"type": 1, "count": c} for b, c in BOSS_TROPHY.items()}
    req["oxide"] = {"type": 2, "count": 4}
    return req


def create_regions(world: "ctrAPWorld"):
    """Build all regions, exits, and locations from JSON definitions."""
    data = json.loads(
        pkgutil.get_data(__package__, "data/world.json").decode("utf-8")
    )

    player, mw = world.player, world.multiworld

    # --- Resolve native-randomization options up front -------------------
    opts = world.options
    do_shuffle = bool(opts.shuffle_warp_pads.value)            # STRETCH gate
    unlock_mode = opts.warppad_unlock_requirements.value       # 0 vanilla / 1 random / 2 no-4-keys
    boss_mode = opts.bossgarage_unlock_requirements.value      # 0 orig4 / 1 same_hub / 2 trophies

    world.warp_pad_ids = _load_warp_pad_ids()
    world.shuffle_warp_pads = do_shuffle

    # Per-pad resolved unlock requirement: {pad_exit_name -> {type,count,colour}}.
    world.warp_pad_unlock = {}
    if unlock_mode in (1, 2):
        for pad_name in _shuffleable_pad_names(world, world.warp_pad_ids):
            world.warp_pad_unlock[pad_name] = _random_pad_req(world, unlock_mode)
    # unlock_mode == 0 (vanilla): leave empty -> keep JSON text rules; emit type:0.

    # Destination shuffle (STRETCH). Identity / empty when off. MVP keeps this
    # empty so warp_pad_map serializes as identity native-side.
    world.warp_pad_map = {}

    # Boss-garage requirements, resolved to flat {type,count}.
    world.boss_garage_req = _resolve_boss_reqs(boss_mode)

    regions = []

    for reg in data["regions"]:
        region = Region(reg["name"], player, mw)
        region.type = reg.get("type", "generic")
        region.is_start = reg.get("is_start", False)
        mw.regions.append(region)
        regions.append(region)

    region_lookup = {r.name: r for r in regions}

    for reg in data["regions"]:
        region = region_lookup[reg["name"]]
        for loc_data in reg.get("locations", []):
            name = loc_data["name"]
            location = create_location(player, name, region)
            location.type = loc_data.get("type", "default")
            location.logic_text = loc_data.get("requires", "True")
            region.locations.append(location)
            mw.regions.location_cache[player][name] = location

    for reg in data["regions"]:
        region = region_lookup[reg["name"]]
        for ex in reg.get("exits", []):
            ent = Entrance(
                player=player,
                name=ex["name"],
                parent=region,
                randomization_group=ex.get("randomization_group"),
                randomization_type=EntranceType[ex.get("randomization_type")],
            )
            ent.access_rule_text = ex.get("access_rule", "True")
            tgt = ex.get("target")
            if tgt in region_lookup:
                ent.connect(region_lookup[tgt])
            region.exits.append(ent)
            mw.regions.entrance_cache[player][ent.name] = ent

    world.start_region = next(
        (r for r in regions if getattr(r, "is_start", False)),
        None
    )
    return regions
