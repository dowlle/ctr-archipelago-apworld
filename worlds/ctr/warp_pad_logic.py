"""Port of CTR-Standalone's get_random_warppad_unlocks for the Archipelago apworld.

Source of truth:
  CTR-Standalone/src/seed_generation/randomize_warppad_requirements.rs
  CTR-Standalone/src/seed_generation/item_randomization/player_inventory.rs
  CTR-Standalone/src/seed_generation/game_world.rs  (WarpPad::new token colours)

Icebound's real algorithm (NOT "force the 4 starters vanilla"):
  1) Pick a RANDOM FREE SUBSET of the 5 N. Sanity Beach pads
     [Crash Cove, Roo's Tubes, Mystery Caves, Sewer Speedway, Skull Rock],
     size weighted [(1,10),(2,30),(3,30),(4,15),(5,15)] -> those pads are FREE
     (requirement None). Every OTHER pad -- including the non-chosen starters --
     gets a real requirement.
  2) SPHERE-SEARCH over the VANILLA location->reward map: seed inventory from the
     free pads' rewards, then repeatedly pick a random reachable still-unassigned
     pad, assign it a requirement whose item TYPE is currently in inventory (so it
     is satisfiable the moment the pad is reached), and add that pad's vanilla
     rewards to inventory. Solvable by construction.
  3) Type weighting + "Any"-variant collapse + post-pass count reduction, all
     ported verbatim from the Rust.

AP adaptation: AP decouples location<->item (real items are placed by
fill_restrictive, not fixed to races). So we run the sphere-search over a SYNTHETIC
vanilla reward map purely to produce a SOLVABLE requirement DAG, then install that
DAG as AP access rules (Rules.add_warp_pad_unlock_rules). Free-subset guarantees
sphere 0 is non-empty; fill_restrictive + reseed handles residual interleaving.

Determinism: every draw uses world.random (AP's per-slot seeded RNG); every dict
iteration that the Rust sorts is sorted here too, so the same YAML + seed
reproduces identical output.
"""

import heapq
import json
import math
import pkgutil
import re


# ---------------------------------------------------------------------------
# Static data -- the vanilla world (track-name strings instead of the Rust enum)
# ---------------------------------------------------------------------------

# Hub-door static gate per shuffleable track, mirroring the AP exit-graph Key
# gates (data/world.json). N. Sanity Beach pads ungated; Lost Ruins behind Key 1;
# Glacier behind Key 2; Citadel behind Key 3; Gem Stone Valley trials behind
# Key 1; Gem Stone Valley gem cups behind Key 2 (the Cups Room hub gate, native
# arrKeysNeeded[GEM_STONE_VALLEY]=2 -- NOT 3). The
# sphere-search reasons over these so it never assigns a requirement behind a Key
# wall it cannot yet pass.
#
# CRYSTAL pads sit at their HUB FLOOR (the open-when-free model): in randomized
# mode with include_battle_arenas ON the vanilla "+1 Key" arena gates are
# stripped in Regions.create_regions, so Skull Rock is a genuine 5th 0-key
# bootstrap pad, Rampage Ruins Key 1, Rocky Road Key 2, Nitro Court Key 3.
# CAVEAT: with include_battle_arenas OFF the live graph keeps the vanilla
# has('Key', hub+1) rules, so these entries are then optimistic by one Key.
# Benign: reachability always comes from the live-graph sweep
# (_reachable_pads_and_collect); HUB_STATIC values feed only the unreachable-
# fallback's cheapest-Key sort heuristic.
HUB_STATIC = {
    # N. Sanity Beach -- no hub gate (Skull Rock crystal at hub floor 0)
    "Crash Cove": [], "Roo's Tubes": [], "Mystery Caves": [],
    "Sewer Speedway": [], "Skull Rock": [],
    # Lost Ruins -- Key 1 (Rampage Ruins crystal at hub floor Key 1)
    "Coco Park": [("Key", 1)], "Tiger Temple": [("Key", 1)],
    "Papu's Pyramid": [("Key", 1)], "Dingo Canyon": [("Key", 1)],
    "Rampage Ruins": [("Key", 1)],
    # Glacier Park -- Key 2 (Rocky Road crystal at hub floor Key 2)
    "Blizzard Bluff": [("Key", 2)], "Dragon Mines": [("Key", 2)],
    "Polar Pass": [("Key", 2)], "Tiny Arena": [("Key", 2)],
    "Rocky Road": [("Key", 2)],
    # Citadel City -- Key 3 (Nitro Court crystal at hub floor Key 3)
    "Hot Air Skyway": [("Key", 3)], "Cortex Castle": [("Key", 3)],
    "N. Gin Labs": [("Key", 3)], "Oxide Station": [("Key", 3)],
    "Nitro Court": [("Key", 3)],
    # Gem Stone Valley TRIAL pads -- behind Key 1 (N. Sanity Beach <-> Gem Stone
    # Valley). Slide Coliseum + Turbo Track have NO trophy race and NO CTR-token
    # challenge: only the 3 relic Time Trials (verified against data/world.json).
    # They are SINGLE-STAGE (no stage 2) but DO get a randomized stage-1 entry
    # requirement (the OPEN model) -- excluded from TROPHY_TRACKS below so the
    # sphere-search assigns them only a tier-1 req. Their vanilla relic/gem JSON
    # gate is REPLACED by this randomized requirement in Rules.add_warp_pad_unlock_rules
    # (keeping only the Key-1 hub gate).
    "Slide Coliseum": [("Key", 1)], "Turbo Track": [("Key", 1)],
    # Gem Stone Valley GEM-CUP pads -- behind Key 3 (the Cups Room hub gate:
    # 'Gem Stone Valley <-> Cups Room' = has('Key', 3) in data/world.json). Each
    # cup yields a Gem on completion ('<Colour> Gem Cup: Gem'). Like the trials they
    # are SINGLE-STAGE (no stage 2) but DO get a randomized stage-1 entry requirement
    # (the OPEN model) -- excluded from TROPHY_TRACKS AND from CUP_TRACKS below so
    # the sphere-search assigns them only a tier-1 req. Their vanilla per-cup
    # has('<Colour> CTR Token', 4) JSON gate is REPLACED by this randomized requirement
    # in Rules.add_warp_pad_unlock_rules, keeping ONLY the Key-3 Cups Room hub gate
    # (the randomized req is ANDed on TOP of that key gate, never replaces it). The
    # track key is '<Colour> Cup' so _pad_exit_name yields '<Colour> Cup Warp Pad'
    # (the AP exit name); the destination region is '<Colour> Gem Cup'. Gem cups are
    # destination-shuffle-eligible (CATEGORY_POOLS['cups'], slot_data v3) when the
    # 'cups' category is selected AND include_gem_cups puts their content in the seed;
    # their UNLOCK REQUIREMENT is randomized on the same include_gem_cups gate (mirrors
    # include_battle_arenas for crystals).
    "Red Cup": [("Key", 2)], "Green Cup": [("Key", 2)], "Blue Cup": [("Key", 2)],
    "Yellow Cup": [("Key", 2)], "Purple Cup": [("Key", 2)],
}

# The two Gem Stone Valley trial pads -- single-stage, randomized stage-1 only.
TRIAL_TRACKS = {"Slide Coliseum", "Turbo Track"}

# The five Gem Stone Valley gem-cup pads -- single-stage, randomized stage-1 only.
# (Track keys, not region names: the region is '<Colour> Gem Cup'.)
CUP_TRACKS = {"Red Cup", "Green Cup", "Blue Cup", "Yellow Cup", "Purple Cup"}

# Vanilla CTR-Token COLOUR per track. Transcribed VERBATIM from game_world.rs
# WarpPad::new (lines 1211-1219): Red/Green/Blue explicit, Yellow = default branch.
TRACK_TOKEN_COLOUR = {
    "Crash Cove": "Red", "Mystery Caves": "Red", "Papu's Pyramid": "Red",
    "Blizzard Bluff": "Red",
    "Roo's Tubes": "Green", "Coco Park": "Green", "Polar Pass": "Green",
    "Cortex Castle": "Green",
    "Sewer Speedway": "Blue", "Tiger Temple": "Blue", "Dragon Mines": "Blue",
    "N. Gin Labs": "Blue",
    # default -> Yellow
    "Dingo Canyon": "Yellow", "Tiny Arena": "Yellow", "Hot Air Skyway": "Yellow",
    "Oxide Station": "Yellow",
}

# Battle-arena crystal pads yield a Purple CTR Token (Rust BattleArenaRewards
# single_reward = PurpleCtrToken).
ARENA_TRACKS = {"Skull Rock", "Rampage Ruins", "Rocky Road", "Nitro Court"}

# The 16 trophy-race pads — the ONLY pads that carry a stage 2 (Icebound's
# WarpPad.unlock_2; game_world.rs:1196-1231). Stage 2 gates that pad's CTR Token
# Challenge + 3 relic Time Trials. The 4 arenas (no stage 2: their crystal
# challenge IS their primary race), the trials (single-stage relic-only) and the
# gem cups (single-stage, gem reward) have none. HUB_STATIC now also holds the 2
# trial pads and the 5 gem-cup pads, so the trophy pads are exactly HUB_STATIC
# minus the arenas, the trials AND the cups.
TROPHY_TRACKS = set(HUB_STATIC) - ARENA_TRACKS - TRIAL_TRACKS - CUP_TRACKS

# NOTE: HUB_STATIC is defined above; TROPHY_TRACKS is finalised after it so the
# set comprehension sees the full dict.

# The 5 N. Sanity Beach candidates for the free subset, weighted sizes.
FREE_CANDIDATES = ["Crash Cove", "Roo's Tubes", "Mystery Caves",
                   "Sewer Speedway", "Skull Rock"]
FREE_SIZE_WEIGHTS = [(1, 10), (2, 30), (3, 30), (4, 15), (5, 15)]
# Minimum number of FREE (open at spawn) bootstrap pads. See run_sphere_search
# step 1 for the rationale (sphere-0 breadth vs AP fill capacity at ~98% density).
_FREE_MIN = 3
# Boss-race Key rewards enter the inventory naturally through the graph sweep
# (boss garages open at Trophy 4/8/12/16 and their boss-race location yields a
# Key in _vanilla_reward), so no separate boss->hub-pad table is needed.


# ---------------------------------------------------------------------------
# Inventory (port of player_inventory.rs)
# ---------------------------------------------------------------------------

class Inv:
    """Mirror of PlayerInventory: capped counts + Any* aggregate lookups."""
    CAPS = {"Trophy": 16, "Key": 4,
            "Red CTR Token": 4, "Green CTR Token": 4, "Blue CTR Token": 4,
            "Yellow CTR Token": 4, "Purple CTR Token": 4,
            "Sapphire Relic": 18, "Gold Relic": 18, "Platinum Relic": 18,
            "Red Gem": 1, "Green Gem": 1, "Blue Gem": 1, "Yellow Gem": 1,
            "Purple Gem": 1}

    _TOKENS = ("Red CTR Token", "Green CTR Token", "Blue CTR Token",
               "Yellow CTR Token", "Purple CTR Token")
    _RELICS = ("Sapphire Relic", "Gold Relic", "Platinum Relic")
    _GEMS = ("Red Gem", "Green Gem", "Blue Gem", "Yellow Gem", "Purple Gem")

    def __init__(self):
        self.items = {k: 0 for k in self.CAPS}

    def add(self, item):
        if item in self.CAPS and self.items[item] < self.CAPS[item]:
            self.items[item] += 1

    def count(self, name):
        if name == "AnyCtrToken":
            return sum(self.items[c] for c in self._TOKENS)
        if name == "AnyRelic":
            return sum(self.items[c] for c in self._RELICS)
        if name == "AnyGem":
            return sum(self.items[c] for c in self._GEMS)
        return self.items.get(name, 0)

    def passes(self, reqs):
        """reqs is a list of (item_name, count); item names map 1:1 (incl Any*)."""
        return all(self.count(name) >= cnt for name, cnt in reqs)


# ---------------------------------------------------------------------------
# Vanilla reward map
# ---------------------------------------------------------------------------

def _token_colour(phys_track, dest_track):
    """CTR-Token colour for a token challenge on phys_track. Prefer the loaded
    (destination) track's colour; fall back to the physical track when the
    destination has none (trial/cup loaded onto a race pad)."""
    if phys_track in ARENA_TRACKS or dest_track in ARENA_TRACKS:
        return "Purple"
    return TRACK_TOKEN_COLOUR.get(dest_track) or TRACK_TOKEN_COLOUR.get(phys_track) or "Red"


def _reward_for(phys_track, dest_track, suffix):
    """Vanilla RaceReward a physical-pad location yields, or None if not a sphere
    reward. The location set belongs to the PHYSICAL pad (its AP region); only
    the token colour is taken from the loaded (dest) track."""
    if suffix == "Trophy Race":
        return "Trophy"
    if suffix == "Sapphire Time Trial":
        return "Sapphire Relic"
    if suffix == "Gold Time Trial":
        return "Gold Relic"
    if suffix == "Platinum Time Trial":
        return "Platinum Relic"
    if suffix == "CTR Token Challenge":
        return f"{_token_colour(phys_track, dest_track)} CTR Token"
    if suffix == "Crystal Bonus Round":
        return "Purple CTR Token"
    return None  # Boss Race / Gem / Oxide handled elsewhere


def _parse_requires(text):
    """Parse a JSON 'requires' string like "has('Trophy', 1) and has('Key', 2)"
    into [(item, count), ...]. Empty / always -> []."""
    text = (text or "").strip()
    if not text or text.lower() in ("true", "always"):
        return []
    out = []
    for part in text.split("and"):
        part = part.strip()
        if not part.startswith("has("):
            continue
        inner = part[4:-1]
        args = [x.strip().strip("'\"") for x in inner.split(",")]
        if not args or not args[0]:
            continue
        item = args[0]
        cnt = int(args[1]) if len(args) > 1 else 1
        out.append((item, cnt))
    return out


def build_graph(world, reward_track_for, include_gem_cups=False):
    """Build a reachability model from the LIVE AP region graph so the sphere
    search reasons over the SAME logic AP fill will enforce.

    Returns (regions, exits, locations) where:
      exits[region]    = [(exit_name, target_region, static_gate)]   (Key doors,
                         boss-garage Trophy gates, hub links; pad-exit gate is the
                         per-seed warp-pad requirement, applied dynamically).
      locations[name]  = {"region","reward","gate","is_tt_or_token","trophy_loc"}
                         reward = the VANILLA reward that race gives (boss->Key,
                         gem cup->Gem, etc.), used to grow the inventory.
    """
    exits = {}
    locations = {}
    region_type = {}
    for region in world.multiworld.get_regions(world.player):
        rname = region.name
        region_type[rname] = getattr(region, "type", "generic")
        ex_list = []
        for ent in region.exits:
            tgt = ent.connected_region.name if ent.connected_region else None
            if tgt is None:
                continue
            gate = _parse_requires(getattr(ent, "access_rule_text", "True"))
            ex_list.append((ent.name, tgt, gate))
        exits[rname] = ex_list
    # locations + vanilla rewards
    for region in world.multiworld.get_regions(world.player):
        rname = region.name
        rtype = region_type[rname]
        dest_track = reward_track_for(rname) if rname in HUB_STATIC else rname
        for loc in region.locations:
            name = loc.name
            gate = _parse_requires(getattr(loc, "logic_text", ""))
            sfx = name.split(":", 1)[1].strip() if ":" in name else name
            reward = _vanilla_reward(rname, rtype, dest_track, sfx, include_gem_cups)
            is_tt = name.endswith("Time Trial") or name.endswith("CTR Token Challenge")
            trophy_loc = None
            if is_tt:
                trophy_loc = name.split(":", 1)[0].strip() + ": Trophy Race"
            locations[name] = {
                "region": rname, "reward": reward, "gate": gate,
                "is_tt_or_token": is_tt, "trophy_loc": trophy_loc,
            }
    return exits, locations, region_type


def _vanilla_reward(region_name, region_type, dest_track, suffix, include_gem_cups=False):
    """Vanilla reward a location yields, for inventory growth in the sphere search.
    Boss races (except Oxide) yield a Key; gem cups yield their Gem ONLY when gem
    cups are part of the seed (include_gem_cups); race/crystal locations yield their
    reward."""
    if region_type == "boss":
        return None if "Oxide" in region_name else "Key"
    if region_type == "cup":
        # Gem cups feed their Gem into the synthetic sphere inventory ONLY when the
        # seed actually contains gem cups (include_gem_cups). That is what lets a gem
        # be CHOSEN as a warp-pad requirement (subject to its REQ_WEIGHTS weight):
        # without the reward in the inventory the sphere search/_choose_requirement
        # never owns a gem, so a gem could never gate. When cups are NOT in the seed
        # the reward stays OUT (legacy behaviour: gems never gate).
        #
        # No circular dependency: cups are pure leaves in the DAG (single-stage, they
        # gate nothing onward), and the sphere search only ASSIGNS a pad its tier-1
        # requirement from items owned BEFORE that pad is reached. A cup's own Gem is
        # added to the inventory only AFTER the cup is collected, so it can never be
        # demanded as that same cup's (or an earlier-opened pad's) entry requirement.
        if include_gem_cups and suffix == "Gem":
            colour = region_name.split()[0]  # "Red Gem Cup" -> "Red"
            gem = f"{colour} Gem"
            if gem in GEM_ITEMS:
                return gem
        return None
    track = region_name
    return _reward_for(track, dest_track, suffix)


# ---------------------------------------------------------------------------
# Requirement weighting + Any* collapse (ports lines 250-366)
# ---------------------------------------------------------------------------

# --- Requirement-weight PRESETS (YAML-tuneable, see Options.RequirementVariety) ---
# trophy_heavy_legacy = the original CTR-apworld weights (Trophy 100, Token 15/10,
# Relic 20, Key 25, Gem 2). icebound_beta5 = Icebound's rebalanced beta5 weights
# (Trophy 90, Token 16/12, Relic 18, Key 20, Gem 4). Both presets share the SAME
# key set, so _STAGE2_ITEMS / the `allowed` filter stay valid across presets.
_REQ_WEIGHTS_TROPHY_HEAVY_LEGACY = {
    "Trophy": 100, "Key": 25,
    "Red CTR Token": 15, "Green CTR Token": 15, "Blue CTR Token": 15,
    "Yellow CTR Token": 15, "Purple CTR Token": 10,
    "Sapphire Relic": 20, "Gold Relic": 20, "Platinum Relic": 20,
    "Red Gem": 2, "Green Gem": 2, "Blue Gem": 2, "Yellow Gem": 2, "Purple Gem": 2,
}
_REQ_WEIGHTS_ICEBOUND_BETA5 = {
    "Trophy": 90, "Key": 20,
    "Red CTR Token": 16, "Green CTR Token": 16, "Blue CTR Token": 16,
    "Yellow CTR Token": 16, "Purple CTR Token": 12,
    "Sapphire Relic": 18, "Gold Relic": 18, "Platinum Relic": 18,
    "Red Gem": 4, "Green Gem": 4, "Blue Gem": 4, "Yellow Gem": 4, "Purple Gem": 4,
}

# Any* collapse parameters per preset. Tuple layout:
#   (token_chance, token_scale, token_cap,
#    relic_chance, relic_scale, relic_cap,
#    gem_chance,   gem_cap)
# A *_cap of None means "no cap". Collapse CHANCES (token 33 / relic 20 / gem 80)
# are unchanged from the original Icebound port; beta5 only retunes scale + caps and
# drops the gem "-1" reduction. custom mode reuses the legacy collapse row.
_ANY_COLLAPSE_PARAMS = {
    "trophy_heavy_legacy": (33, 0.6, None, 20, 0.3, None, 80, None),
    "icebound_beta5":      (33, 0.8, 16,   20, 0.5, 27,   80, 5),
    "custom":              (33, 0.6, None, 20, 0.3, None, 80, None),
}

# Active weight table + collapse params. Initialised to the LEGACY defaults so the
# module is importable/usable before _load_requirement_preset(world) runs; the loader
# overwrites these from the chosen preset at run_sphere_search() start. Default seed
# generation uses icebound_beta5 (see Options.RequirementVariety.default = 0).
REQ_WEIGHTS = dict(_REQ_WEIGHTS_TROPHY_HEAVY_LEGACY)
# Any*-aggregate expression mode. True = any_of: a collapsed Any* requirement
# stays a genuine "any N of type" aggregate (emitted as native type 6/7/8).
# ALWAYS TRUE since the 2026-07-15 release polish: the former
# `requirement_specificity` YAML option existed only as a compatibility escape
# hatch for native builds without the any-of aggregate patch, which every
# release build has. The False (specific_colour) flatten path via _resolve_any
# is kept in code but is no longer reachable from options.
_ANY_OF_MODE = True
_TOKEN_COLLAPSE_CHANCE = 33
_TOKEN_COLLAPSE_SCALE = 0.6
_TOKEN_COLLAPSE_CAP = None
_RELIC_COLLAPSE_CHANCE = 20
_RELIC_COLLAPSE_SCALE = 0.3
_RELIC_COLLAPSE_CAP = None
_GEM_COLLAPSE_CHANCE = 80
_GEM_COLLAPSE_CAP = None

TOKEN_ITEMS = ("Red CTR Token", "Green CTR Token", "Blue CTR Token",
               "Yellow CTR Token", "Purple CTR Token")
RELIC_ITEMS = ("Sapphire Relic", "Gold Relic", "Platinum Relic")
GEM_ITEMS = ("Red Gem", "Green Gem", "Blue Gem", "Yellow Gem", "Purple Gem")


def effective_custom_weights(world):
    """The requirement-weight table for requirement_variety=custom: the legacy
    defaults overlaid with the player's requirement_weights, keeping only valid
    keys so the key universe stays stable. Pure -- reads options, mutates no
    module state. Shared by _load_requirement_preset (the live weight loader) and
    __init__.generate_early's zero-Trophy guard (issue #87) so both read the exact
    same effective weights."""
    weights = dict(_REQ_WEIGHTS_TROPHY_HEAVY_LEGACY)  # fallback for omitted keys
    custom = getattr(getattr(world.options, "requirement_weights", None),
                     "value", None) or {}
    for k, v in custom.items():
        if k in weights:  # ignore stray keys; keep the key universe stable
            weights[k] = v
    return weights


def _load_requirement_preset(world):
    """Load the requirement-weight preset chosen by the requirement_variety YAML
    option into the module-level REQ_WEIGHTS + the eight Any*-collapse globals.

    MUST be called at run_sphere_search() start (before REQ_WEIGHTS / the `allowed`
    filter are read), and re-called on every invocation -- the state is module-global
    and never cached on the world, so a second seed in the same process always
    reloads its own preset.

    - icebound_beta5 (default): beta5 weights + retuned collapse (Token x0.8 cap 16,
      Relic x0.5 cap 27, Gem cap 5, no -1).
    - trophy_heavy_legacy: original weights + original collapse (x0.6 / x0.3 / -1).
    - custom: start from the legacy weights, then overlay requirement_weights; any
      omitted item keeps its legacy weight. Unrecognised custom keys are ignored
      (OptionDict.valid_keys already constrains them at parse time). custom uses the
      legacy collapse row.

    A missing requirement_variety option (e.g. an old YAML) safely falls back to the
    legacy preset.
    """
    global REQ_WEIGHTS
    global _TOKEN_COLLAPSE_CHANCE, _TOKEN_COLLAPSE_SCALE, _TOKEN_COLLAPSE_CAP
    global _RELIC_COLLAPSE_CHANCE, _RELIC_COLLAPSE_SCALE, _RELIC_COLLAPSE_CAP
    global _GEM_COLLAPSE_CHANCE, _GEM_COLLAPSE_CAP
    global _ANY_OF_MODE

    # any_of is the only mode since the 2026-07-15 release polish (the
    # requirement_specificity option was removed; see the module-global note).
    _ANY_OF_MODE = True

    variety_opt = getattr(world.options, "requirement_variety", None)
    # Choice options expose .current_key ("icebound_beta5" etc.); fall back to legacy.
    preset = getattr(variety_opt, "current_key", "trophy_heavy_legacy")

    if preset == "icebound_beta5":
        REQ_WEIGHTS = dict(_REQ_WEIGHTS_ICEBOUND_BETA5)
        collapse_key = "icebound_beta5"
    elif preset == "custom":
        REQ_WEIGHTS = effective_custom_weights(world)
        collapse_key = "custom"
    else:  # trophy_heavy_legacy + any unknown/missing value
        REQ_WEIGHTS = dict(_REQ_WEIGHTS_TROPHY_HEAVY_LEGACY)
        collapse_key = "trophy_heavy_legacy"

    (_TOKEN_COLLAPSE_CHANCE, _TOKEN_COLLAPSE_SCALE, _TOKEN_COLLAPSE_CAP,
     _RELIC_COLLAPSE_CHANCE, _RELIC_COLLAPSE_SCALE, _RELIC_COLLAPSE_CAP,
     _GEM_COLLAPSE_CHANCE, _GEM_COLLAPSE_CAP) = _ANY_COLLAPSE_PARAMS[collapse_key]

    _load_two_stage_density(world)


# two_stage_density presets: (real-gate cap per seed, per-pad collapse chance %).
# "standard" MUST stay byte-identical to the pre-option constants (6, 35): same
# values, and the diversity discount stays disabled (k=0) so the weights passed to
# rnd.choices are the untouched ints. "off" uses cap 0 (the cap short-circuits
# before the collapse roll, so every stage 2 echoes its stage 1 and consumes no
# RNG on the roll -- deliberate, documented in the option).
_TWO_STAGE_DENSITY_PARAMS = {
    # "off" no longer reaches this table: since the 2026-07-15 release polish it
    # short-circuits in Regions.py as collapse_stage2=True (the former autounlock
    # behaviour -- stage 2 literally free). The row is kept as a safe fallback.
    "off":      (0, 100),
    "light":    (4, 50),
    "standard": (6, 35),
    "deep":     (10, 20),
    # "full": every trophy pad that CAN carry a real stage-2 gate gets one -- cap
    # = all 16 trophy pads, no random collapse. Only the golden-path guard (a)
    # still collapses (nothing ownable backs a gate). The densest legal seeds.
    "full":     (16, 0),
}

# Within-seed diminishing-repeat discount (T6, deep-dive 2026-07-11): each
# requirement FAMILY's weight is divided by (1 + k * families_assigned_so_far).
# Active ONLY at non-standard two_stage_density (T1 re-baseline: type shares are
# in band at the default, but real stage-2 draws run 56-59% Trophy, so a raised
# cap needs this pressure or the extra gates come out Trophy-shaped). k is
# internal, not a YAML knob. No new RNG draws: only the weights fed to the
# existing rnd.choices call change, so determinism is preserved.
_DIVERSITY_K = 0.0
_DIVERSITY_COUNTS = {}


def _req_family(item):
    """Map a requirement item (concrete or Any* aggregate) to its weight family."""
    if item in TOKEN_ITEMS or item == "AnyCtrToken":
        return "Token"
    if item in RELIC_ITEMS or item == "AnyRelic":
        return "Relic"
    if item in GEM_ITEMS or item == "AnyGem":
        return "Gem"
    return item  # Trophy, Key


def _note_assigned_requirement(req):
    """Record a KEPT requirement's family for the diversity discount. Called only
    at the two primary assignment sites in run_sphere_search (stage-1 pad reqs and
    real stage-2 gates); collapsed echoes and revalidation relaxations do not add
    diversity pressure."""
    if req is None:
        return
    fam = _req_family(req[0])
    _DIVERSITY_COUNTS[fam] = _DIVERSITY_COUNTS.get(fam, 0) + 1


def _load_two_stage_density(world):
    """Load the two_stage_density option into the module globals. Called from
    _load_requirement_preset (i.e. at every run_sphere_search start), so a second
    seed in the same process always reloads its own values. A missing option (old
    YAML) falls back to standard = the pre-option constants."""
    global _STAGE2_REAL_CAP, _STAGE2_COLLAPSE_CHANCE, _DIVERSITY_K, _DIVERSITY_COUNTS
    opt = getattr(world.options, "two_stage_density", None)
    key = getattr(opt, "current_key", "standard")
    if key not in _TWO_STAGE_DENSITY_PARAMS:
        key = "standard"
    _STAGE2_REAL_CAP, _STAGE2_COLLAPSE_CHANCE = _TWO_STAGE_DENSITY_PARAMS[key]
    _DIVERSITY_K = 0.0 if key == "standard" else 0.5
    _DIVERSITY_COUNTS = {}


def _weighted_choice(rnd, pairs):
    """pairs = [(value, weight)]; returns one value via rnd.choices."""
    values = [v for v, _ in pairs]
    weights = [w for _, w in pairs]
    return rnd.choices(values, weights=weights, k=1)[0]


def _choose_requirement(rnd, inv, allowed=None):
    """Port of lines 268-366: pick an owned item type, weight it, maybe collapse
    to an Any* aggregate. Returns (req_item, count) or None when no candidate is
    eligible. Any* is resolved to a concrete owned colour by the caller
    (run_sphere_search) so native needs no 'any' aggregate support.

    `allowed` (optional set of item names) restricts which item TYPES may be chosen
    as a requirement -- used to exclude relic tiers that the relic-progression
    sliders have pinned mostly OUT of the multiworld pool (a low-slider tier is not
    a freely-placeable progression item, so requiring it under reward-agnostic AP
    fill creates a circular, hard-to-seat gate). The excluded relics still grow the
    synthetic inventory (so AnyRelic aggregates count them); they just are not
    picked as a concrete requirement. This is the design rule "if a seed is tight, make do
    with the other item types" turned into a sphere-search rule -- the sliders stay
    authoritative and are never silently overridden."""
    pool_items = REQ_WEIGHTS if allowed is None else [
        it for it in REQ_WEIGHTS if it in allowed]
    cands = [(it, inv.items[it]) for it in pool_items if inv.items[it] > 0]
    if not cands:
        return None
    cands.sort()  # Rust sorts possible_reqs before weighting
    if _DIVERSITY_K:
        # Diminishing-repeat discount (see _DIVERSITY_K above). Guarded so the
        # standard path passes the untouched int weights (byte-identical draws).
        pairs = [(c, REQ_WEIGHTS[c[0]]
                  / (1.0 + _DIVERSITY_K * _DIVERSITY_COUNTS.get(_req_family(c[0]), 0)))
                 for c in cands]
    else:
        pairs = [(c, REQ_WEIGHTS[c[0]]) for c in cands]
    chosen = _weighted_choice(rnd, pairs)
    req_item, req_cnt = chosen[0], chosen[1]

    # Any* collapse stays scoped to the colours/tiers actually allowed: AnyRelic
    # aggregates only the relic tiers in `allowed` so a lowered concrete colour is
    # never an excluded (pinned-out) tier.
    if req_item in TOKEN_ITEMS:
        if rnd.randrange(100) < _TOKEN_COLLAPSE_CHANCE:
            total = inv.count("AnyCtrToken")
            cnt = max(1, math.ceil(total * _TOKEN_COLLAPSE_SCALE))
            if _TOKEN_COLLAPSE_CAP is not None:
                cnt = min(cnt, _TOKEN_COLLAPSE_CAP)
            req_item, req_cnt = "AnyCtrToken", cnt
    elif req_item in RELIC_ITEMS:
        if rnd.randrange(100) < _RELIC_COLLAPSE_CHANCE:
            tiers = [r for r in RELIC_ITEMS if allowed is None or r in allowed]
            total = sum(inv.items[r] for r in tiers)
            cnt = max(1, math.ceil(total * _RELIC_COLLAPSE_SCALE))
            if _RELIC_COLLAPSE_CAP is not None:
                cnt = min(cnt, _RELIC_COLLAPSE_CAP)
            req_item, req_cnt = "AnyRelic", cnt
    elif req_item in GEM_ITEMS:
        if rnd.randrange(100) < _GEM_COLLAPSE_CHANCE:
            total = inv.count("AnyGem")
            # Legacy preset (cap None) keeps Rust's per-item "-1" (count - 1, floored
            # at 1). beta5 drops the -1 and clamps to _GEM_COLLAPSE_CAP instead.
            if _GEM_COLLAPSE_CAP is None:
                cnt = max(1, total - 1)
            else:
                cnt = max(1, min(total, _GEM_COLLAPSE_CAP))
            req_item, req_cnt = "AnyGem", cnt
    return (req_item, req_cnt)


def _resolve_any(inv, req, allowed=None):
    """Lower an Any* requirement to the single owned colour with the most copies,
    so the AP rule + slot_data emit a concrete {type,colour,count} that Inv has
    proven is owned. Keeps solvability and avoids native 'any' support. When
    `allowed` is given, the lowered colour/tier is restricted to it (so AnyRelic
    never resolves to a pinned-out relic tier).

    requirement_specificity = any_of (the new default, _ANY_OF_MODE True): do NOT
    flatten -- return the Any* requirement unchanged so it carries through to logic
    and slot_data as a genuine "any N of type" aggregate (native type 6/7/8). The
    aggregate is satisfiable by construction: the caller clamps the count to
    inv.count(Any*) which already sums every colour/tier owned at this sphere. Only
    requirement_specificity = specific_colour (_ANY_OF_MODE False, legacy) flattens
    to a single concrete colour below."""
    item, cnt = req
    if _ANY_OF_MODE and item in ("AnyCtrToken", "AnyRelic", "AnyGem"):
        return req
    if item == "AnyCtrToken":
        pool = Inv._TOKENS
    elif item == "AnyRelic":
        pool = Inv._RELICS
    elif item == "AnyGem":
        pool = Inv._GEMS
    else:
        return req
    if allowed is not None:
        pool = tuple(c for c in pool if c in allowed) or pool
    # pick the owned colour with the most copies (deterministic: sorted tie-break)
    best = max(sorted(pool), key=lambda c: inv.items[c])
    cnt = min(cnt, max(1, inv.items[best]))  # never exceed what is owned
    return (best, cnt)


# ---------------------------------------------------------------------------
# Sphere search (port of the `while !empty` loop)
# ---------------------------------------------------------------------------

def _max_key(reqs):
    return max((c for n, c in reqs if n == "Key"), default=0)


def _pad_exit_name(track):
    return f"{track} Warp Pad"


_VANILLA_PAD_TARGET = None


def _vanilla_pad_targets():
    """{pad_exit_name -> the region that pad vanilla-loads}, from the PRISTINE
    data/world.json exit targets (NOT the live, possibly destination-rewired
    graph). Used to build the identity-topology view of the sweep graph. Cached
    (static data)."""
    global _VANILLA_PAD_TARGET
    if _VANILLA_PAD_TARGET is None:
        data = json.loads(
            pkgutil.get_data(__package__, "data/world.json").decode("utf-8"))
        pads = json.loads(
            pkgutil.get_data(__package__,
                             "data/warp_pad_ids.json").decode("utf-8"))["pads"]
        tgt = {}
        for r in data["regions"]:
            for ex in r.get("exits", []):
                if ex["name"] in pads and ex.get("target") is not None:
                    tgt[ex["name"]] = ex["target"]
        _VANILLA_PAD_TARGET = tgt
    return _VANILLA_PAD_TARGET


def _identity_exits(exits):
    """Copy of a build_graph exits dict with every warp-pad exit re-targeted to
    the region it vanilla-loads -- the identity-topology view. The live AP graph
    is rewired to shuffled destinations by create_regions BEFORE the sweep runs,
    so identity must be reconstructed here explicitly. Exits keep their physical
    static gates (hub floors); only the target region changes."""
    vanilla = _vanilla_pad_targets()
    return {
        region: [(name, vanilla.get(name, tgt), gate)
                 for (name, tgt, gate) in ex_list]
        for region, ex_list in exits.items()
    }


def _free_candidates_live(exits, start):
    """The pads genuinely open at sphere 0 in THIS seed's graph: host region
    reachable and pad-exit static gate satisfied with an EMPTY inventory.
    Derived from the live geography, never a hardcoded list or count: with
    battle arenas included (crystal pads at their hub floor) this is the 5
    N. Sanity pads including Skull Rock; with arenas excluded (vanilla crystal
    gates) it is the 4 race pads. Ordered canonically (legacy candidate order
    first, then any others sorted) so RNG consumption stays stable when the
    geography matches the legacy list."""
    pad_exit_to_track = {_pad_exit_name(t): t for t in HUB_STATIC}
    zero = set()
    seen = {start}
    frontier = [start]
    while frontier:
        cur = frontier.pop()
        for exit_name, tgt, gate in exits.get(cur, []):
            track = pad_exit_to_track.get(exit_name)
            if track is not None:
                if not gate:  # empty static gate == open at 0 items
                    zero.add(track)
                continue
            if tgt in seen or gate:
                continue  # gated non-pad exits are closed at 0 items
            seen.add(tgt)
            frontier.append(tgt)
    legacy_first = [t for t in FREE_CANDIDATES if t in zero]
    return legacy_first + sorted(zero - set(legacy_first))


def _sphere0_breadth(world, out, reward_track_for, include_gem_cups):
    """How many CTR locations a FINISHED requirement DAG leaves open at ZERO items.

    This is the "sphere-0 breadth" the fill-tail repair below is measured against.
    It mirrors _reachable_pads_and_collect's traversal exactly, but with a
    permanently empty inventory and no collection: BFS the live graph from the
    start region, traverse a warp-pad exit only when that pad is FREE
    (out[track][1] is None) and its static gate passes, then count every location
    whose own gate passes -- with the same two-stage hold-back, so a trophy-track
    TT / token location only counts when that destination's stage 2 is OPEN
    (out[phys][2] is None).

    `out` is run_sphere_search's return shape: {physical_track: {1: req, 2: req}}.
    Stage 2 is keyed there by PHYSICAL pad, so it is re-keyed to destination track
    here (reward_track_for) to match where the locations actually live.

    Pure read-only: writes nothing to `world` and consumes no RNG, so calling it
    between sphere-search attempts cannot perturb generation determinism.
    """
    exits, locations, _ = build_graph(world, reward_track_for, include_gem_cups)
    start = world.start_region.name if world.start_region else "Menu"
    pad_reqs = {t: out[t][1] for t in out}
    s2_by_region = {reward_track_for(t): out[t][2] for t in out}
    inv = Inv()

    def passes(reqs):
        return all(inv.count(i) >= c for i, c in reqs)

    pad_exit_to_track = {_pad_exit_name(t): t for t in HUB_STATIC}
    seen = {start}
    frontier = [start]
    while frontier:
        cur = frontier.pop()
        for exit_name, tgt, gate in exits.get(cur, []):
            if tgt in seen or not passes(gate):
                continue
            track = pad_exit_to_track.get(exit_name)
            if track is not None:
                req = pad_reqs.get(track, "UNSET")
                if req == "UNSET":
                    continue
                if req is not None and not passes([req]):
                    continue
            seen.add(tgt)
            frontier.append(tgt)

    n = 0
    for name, meta in locations.items():
        if meta["region"] not in seen or not passes(meta["gate"]):
            continue
        if meta["is_tt_or_token"]:
            tl = locations.get(meta["trophy_loc"])
            if tl is None or tl["region"] not in seen or not passes(tl["gate"]):
                continue
            region = meta["region"]
            if region in TROPHY_TRACKS:
                s2 = s2_by_region.get(region, "UNSET")
                if s2 == "UNSET":
                    continue
                if s2 is not None and not passes([s2]):
                    continue
        n += 1
    return n


def _reachable_pads_and_collect(inv, exits, locations, pad_reqs, stage2_reqs,
                                collected, start):
    """Sweep the AP graph with the current inventory + the per-pad requirements
    decided so far, collecting every reachable location's vanilla reward into the
    inventory (to a fixed point). Returns the set of OPEN, still-unassigned pads
    whose pad-exit is now traversable (candidates for the next requirement).

    A warp-pad exit (named '<track> Warp Pad') is traversable iff its static gate
    passes AND the pad is either free/assigned (pad_reqs has it -> its requirement,
    None=free, is enforced) OR it is the pad we are about to assign (handled by the
    caller: unassigned pads are treated as OPEN with NO extra requirement here, so
    we discover which pads are *reachable to assign*).

    TWO-STAGE: a trophy pad's CTR-token / relic-race rewards (its STAGE-2 content)
    are NOT collected until that pad's stage 2 is (a) assigned and (b) satisfied by
    the current inventory. stage2_reqs is keyed by DESTINATION track (== the region
    the location lives in, == the 16 trophy tracks, since the race shuffle group
    permutes the trophy pads only among themselves). A region not yet in
    stage2_reqs (sentinel 'UNSET') means stage 2 is still closed -> its relic/token
    rewards stay out of inventory (mirrors Icebound holding second_stage_unlocks
    back until the same pad's stage 1 is collected)."""
    pad_exit_to_track = {_pad_exit_name(t): t for t in HUB_STATIC}

    def passes(reqs):
        return all(inv.count(i) >= c for i, c in reqs)

    changed = True
    open_unassigned = set()
    while changed:
        changed = False
        # BFS regions
        seen = {start}
        frontier = [start]
        while frontier:
            cur = frontier.pop()
            for exit_name, tgt, gate in exits.get(cur, []):
                if tgt in seen:
                    continue
                if not passes(gate):
                    continue
                track = pad_exit_to_track.get(exit_name)
                if track is not None:
                    # warp-pad exit: enforce the assigned requirement if any.
                    req = pad_reqs.get(track, "UNSET")
                    if req == "UNSET":
                        # unassigned pad reachable to assign; do NOT traverse its
                        # rewards yet (its requirement isn't decided), but record it.
                        open_unassigned.add(track)
                        continue
                    if req is not None and not passes([req]):
                        continue  # assigned requirement not yet met
                    # req is None -> free bootstrap pad: truly open (no vanilla
                    # trophy floor; the randomizer owns all entry requirements).
                seen.add(tgt)
                frontier.append(tgt)
        # collect rewards from reachable locations
        for name, meta in locations.items():
            if name in collected or meta["region"] not in seen:
                continue
            if not passes(meta["gate"]):
                continue
            if meta["is_tt_or_token"]:
                tl = meta["trophy_loc"]
                tlm = locations.get(tl)
                if tlm is None or tlm["region"] not in seen or not passes(tlm["gate"]):
                    continue
                # STAGE-2 gate: relic-race / CTR-token-challenge content on the 16
                # trophy pads opens only once that pad's stage 2 is assigned AND met.
                region = meta["region"]
                if region in TROPHY_TRACKS:
                    s2 = stage2_reqs.get(region, "UNSET")
                    if s2 == "UNSET":
                        continue  # stage 2 not yet assigned -> content still closed
                    if s2 is not None and not passes([s2]):
                        continue  # stage-2 requirement not yet satisfied
            if meta["reward"]:
                inv.add(meta["reward"])
            collected.add(name)
            changed = True
    return open_unassigned


def _assign_from_inv(rnd, inv, allowed=None):
    """Pick a STAGE-1 requirement satisfiable from the CURRENT inventory. Returns
    (item, count) or None when nothing eligible is owned. Item TYPE is always one
    currently owned (and, if `allowed` is given, one of the non-pinned-out types),
    so the requirement is satisfiable the instant the pad is reached -> solvable by
    construction. Any* is lowered to a concrete owned colour and clamped to owned."""
    req = _choose_requirement(rnd, inv, allowed)
    if req is None:
        return None
    req = _resolve_any(inv, req, allowed)  # lower Any* to a concrete owned colour
    item, cnt = req
    owned = inv.count(item)
    return (item, min(cnt, owned)) if owned > 0 else None


# Stage-2 requirements draw from the SAME full item universe as stage 1
# (Trophy / Key / every CTR-token colour / every relic tier / every gem) -- the
# OPEN model: a pad's tier-2 requirement may be ANY CTR item, with the same
# weighting + Any*-collapse discipline as tier 1. Reward PINNING is gone (relics +
# tokens flow through the normal multiworld pool + the relic-tier sliders), so a
# "3 Blue tokens" stage-2 req is satisfied by AP placing 3 Blue CTR Token
# progression items anywhere reachable before that gate, not by a fixed challenge
# reward. Solvability is preserved by construction: _assign_stage2_from_inv only
# ever picks item TYPES currently owned in the synthetic sphere inventory (so the
# req is satisfiable the instant that stage opens), and the per-pad relaxation
# fallback (run_sphere_search) collapses a stage 2 to equal its stage 1 if the
# inventory cannot yet back any requirement.
_STAGE2_ITEMS = tuple(REQ_WEIGHTS.keys())  # Trophy, Key, tokens, relics, gems

# Baseline per-pad chance that a trophy pad's tier 2 collapses to equal its tier 1
# even when a real tier-2 requirement IS satisfiable. Two-stage stays the DEFAULT
# experience (most pads keep a real, distinct tier-2 gate), but a minority collapse
# to relieve AP fill_restrictive pressure: a collapsed tier 2 adds NO gate beyond the
# trophy race (the TT/token opens the instant the race is reached), which frees
# reachable location capacity for fill to seat the progression that opens the
# remaining real gates. This is the design rule "tier 2 MAY collapse if a seed
# needs it" turned into a small uniform relief valve; the golden path is unaffected
# (tier 1 is always satisfiable-by-construction). Tuned empirically against the
# two-stage-active FillError tail (see the impl A/B sweep).
# NOTE: this and _STAGE2_REAL_CAP are import-time defaults (= the "standard"
# preset); _load_two_stage_density overwrites both per run from the
# two_stage_density YAML option.
_STAGE2_COLLAPSE_CHANCE = 35
# Deterministic cap on the number of REAL (non-collapsed) stage-2 gates per seed.
# Bounds how many distinct second-stage requirements AP fill_restrictive must order,
# which is the lever that actually closes the tight-seed FillError tail (CTR's pool
# is ~98% progression in every config, so a density signal is useless). Set well
# above the count a normal seed produces so two-stage stays the DEFAULT experience;
# only the latest-sphere pads on the densest seeds collapse to tier 1. Tuned with
# the impl A/B sweep.
_STAGE2_REAL_CAP = 6

# Hard ceiling on a tier-2 requirement count (non-Key items). See _post_process /
# run_sphere_search step 3 for the rationale (gameplay + fill-capacity).
_STAGE2_COUNT_CEILING = 4
# Generous ceiling on a tier-1 entry count (non-Key items): only trims the extreme
# Icebound outliers (e.g. "14 trophies to open one pad") that both play as a wall
# and starve fill_restrictive of ordering freedom in maximally tight seeds; the
# vast majority of stage-1 reqs sit well below it, so fidelity is essentially
# preserved. Pure lowering -> solvable DAG preserved.
_STAGE1_COUNT_CEILING = 8


def _assign_stage2_from_inv(rnd, inv, allowed=None):
    """Pick a STAGE-2 requirement from the owned inventory across the FULL item
    universe (Trophy / Key / tokens / relics / gems), minus any relic tiers the
    sliders pinned mostly out of the pool (`allowed`). Reuses the exact stage-1
    chooser (_choose_requirement: weighted pick + per-family Any* collapse), then
    lowers Any* to a concrete owned colour and clamps to owned. Returns (item,count)
    or None when nothing eligible is owned (early bootstrap -> the caller leaves
    stage 2 free / collapses it to stage 1)."""
    req = _choose_requirement(rnd, inv, allowed)  # full-universe weighted + Any* collapse
    if req is None:
        return None
    item, cnt = _resolve_any(inv, req, allowed)   # lower Any* to a concrete owned colour
    owned = inv.count(item)
    return (item, min(cnt, owned)) if owned > 0 else None


def _run_sphere_search_once(world, mode, reward_track_for=None,
                            collapse_stage2=False, include_gem_cups=False):
    """ONE roll of the sphere search. Public entry point is run_sphere_search
    below, which re-rolls this until sphere-0 breadth is wide enough (see the
    comment block there).

    Returns {track_name: {1: stage1_req, 2: stage2_req}} for all shuffleable
    pads. Each req is (item, count) or None (free / no-gate). Stage 2 is non-None
    only for the 16 trophy pads (others get 2: None). mode 2 = random_without_4_keys.
    Deterministic on world.random.

    collapse_stage2 (= two_stage_density "off"; absorbed the former
    autounlock_ctrchallenge_relicrace toggle, 2026-07-15): when True, every
    stage 2 is left OPEN (no requirement) -- Icebound's clear_stage2_unlocks,
    which overwrites every Stage-Two requirement to Trophy x0 so the relic/token
    menu opens the instant the trophy race is beaten. The pad's TT/token rewards
    then collect as soon as the trophy race is reachable (no stage-2 hold-back).

    AP-correct, graph-driven port: reachability is computed over the LIVE AP region
    graph (the exact logic AP fill enforces), so every requirement assigned to a
    pad/stage is provably satisfiable by items collectable strictly BEFORE that
    pad/stage opens -> the produced DAG is solvable by construction under AP's real
    rules.

    TWO-STAGE (Icebound port): a trophy pad's stage 2 (its CTR Token Challenge + 3
    relic Time Trials) is assigned only AFTER that pad's stage 1 (Trophy Race) is
    collected, drawing from the inventory at that moment -- so a stage-2 requirement
    can reference items from earlier-opened pads but never the pad's own (still
    locked) relics/tokens. Mirrors randomize_warppad_requirements.rs:210-217,408-418.

    reward_track_for(track) -> the track this physical pad actually loads (handles
    destination shuffle); defaults to identity. Stage 2 is keyed internally by the
    DESTINATION track (where the relic/token locations live); the caller re-keys it
    to the physical pad for the slot_data contract.

    IDENTITY-TOPOLOGY + RE-VALIDATION (two-phase, active only under destination
    shuffle): the DAG is built on an identity view of the graph (pad exits
    re-targeted to their vanilla regions) so the boss-Key cascade always fires
    and requirements stay rich and varied, then re-validated against the actual
    shuffled graph (_revalidate_against_shuffle), relaxing only the requirements
    that fail there. With shuffle off the sweep runs directly on the live graph
    exactly as before (single phase, byte-identical draws).
    """
    rnd = world.random
    # Load the requirement-weight preset (icebound_beta5 default) into the module
    # globals BEFORE REQ_WEIGHTS / the `allowed` filter below are read. Re-run every
    # call so multi-seed processes never inherit a previous seed's preset.
    _load_requirement_preset(world)
    if reward_track_for is None:
        reward_track_for = lambda t: t

    # Slider-aware requirement filter (a generation-control knob, honoured not
    # overridden). A relic-progression slider below 100 PINS a random ~ (100-slider)%
    # of that tier's 18 relics out of the multiworld pool. The synthetic sphere
    # inventory grows ALL 18 vanilla relics (it cannot know which AP will pin), so a
    # relic stage-1/stage-2 requirement drawn from it can demand MORE copies of a
    # tier than actually exist in the pool (e.g. 'Gold Relic x11' when the slider=50
    # leaves only ~9 findable) -> an impossible gate -> the FillError tail. To stay
    # provably satisfiable under AP's real pool we only allow a relic tier to be
    # CHOSEN as a requirement when its slider is 100 (every relic of that tier is a
    # freely-placeable progression item). Below 100 the tier is excluded from
    # requirement choice (it still grows the inventory so AnyRelic aggregates of the
    # FULL tiers stay correct, and the tier's own relics still appear as findable
    # progression). Trophy / Key / tokens / gems are always allowed -- the seed
    # "makes do with the other item types" by design; the sliders
    # are never silently overridden, only respected as the scarcity signal they are.
    # Default sliders (S100/G100/P0): sapphire+gold usable, platinum excluded.
    _slider = {
        "Sapphire Relic": getattr(world.options, "sapphire_relic_progression").value,
        "Gold Relic": getattr(world.options, "gold_relic_progression").value,
        "Platinum Relic": getattr(world.options, "platinum_relic_progression").value,
    }
    allowed = {it for it in REQ_WEIGHTS
               if it not in RELIC_ITEMS or _slider.get(it, 0) >= 100}

    # The LIVE graph (destination-rewired by create_regions when shuffle is
    # on): this is what AP fill enforces and what the re-validation pass walks.
    exits_real, locations_real, _ = build_graph(
        world, reward_track_for, include_gem_cups)
    start = world.start_region.name if world.start_region else "Menu"

    # IDENTITY-TOPOLOGY DAG (stage-2 starvation fix). Destination shuffle breaks
    # the sweep's bootstrap chain (collect 4 trophy races -> boss 1 opens ->
    # Key 1 -> next hub -> ...): with trophy destinations scattered across all
    # pads the synthetic inventory freezes below Trophy 4 and most pads drain
    # through the unreachable fallback with trivial requirements. Fix: build the
    # requirement DAG on the IDENTITY topology (trophy races on trophy pads, so
    # the sweep always cascades and assigns rich, varied gates), then RE-VALIDATE
    # it against the actual shuffled graph after the post-pass, relaxing only
    # the requirements that fail there (_revalidate_against_shuffle). A
    # requirement is a property of a pad's ENTRY; the shuffle is about content.
    pad_ids = getattr(world, "warp_pad_ids", {})
    wpm = getattr(world, "warp_pad_map", {}) or {}
    shuffle_active = any(
        pad_ids.get(pad, {}).get("level_id") != dest
        for pad, dest in wpm.items())
    if shuffle_active:
        _ex_live, locations_id, _ = build_graph(
            world, lambda t: t, include_gem_cups)
        exits, locations = _identity_exits(_ex_live), locations_id
    else:
        exits, locations = exits_real, locations_real

    # 1) free subset of the sphere-0 bootstrap candidates (live-derived from
    # THIS seed's graph: the pads whose host region and static gate are open at
    # zero items -- see _free_candidates_live; never a hardcoded list). FULLY
    # random: a random-sized (weighted 1..5) random sample, no pinned pad. In randomized mode the vanilla trophy
    # floor is gone (see to_slot_req / create_regions), so EVERY free pad is truly
    # open from an empty inventory and any one of them can bootstrap the sphere.
    #
    # MINIMUM bootstrap breadth (_FREE_MIN): a narrow free subset opens only a few
    # locations at sphere 0, and on a maximally tight seed (CTR's pool is ≈ 98%
    # progression in every config) that starves AP fill_restrictive of the early
    # free slots it needs to seat the items the next pads' stage-1 gates demand ->
    # a (fully reachable but) un-greedily-fillable seed. Each free pad adds ~5
    # sphere-0 locations, so widening the floor is the single most effective lever
    # against the extreme-density FillError tail (empirically ~0.28% at floor 2 ->
    # ~0.08% at floor 3 over a 2500-config sweep). Floor 3 is a small, gameplay-safe
    # deviation from Icebound's 1..5 weighting that strengthens the golden-path
    # guarantee (collecting always unlocks something new). Sizes >= the floor keep
    # their original relative weights.
    free_candidates = _free_candidates_live(exits, start)
    size = max(_FREE_MIN, _weighted_choice(rnd, FREE_SIZE_WEIGHTS))
    size = min(size, len(free_candidates))
    free = rnd.sample(free_candidates, size)

    pad_reqs = {t: None for t in free}  # stage-1 reqs (physical-track keyed)
    # stage2_reqs: dest-track keyed; only the 16 trophy tracks. When collapsed
    # (autounlock), pre-set every trophy track to None (= open, no stage-2 gate)
    # so the loop never assigns one and collection never holds rewards back.
    stage2_reqs = {t: None for t in TROPHY_TRACKS} if collapse_stage2 else {}

    # dest-track -> physical-pad track, so a stage-2 fallback can collapse to the
    # SAME pad's stage-1 requirement. Under destination shuffle the locations of
    # dest D live in region D, but D's pad ENTRY requirement is the physical pad P
    # with reward_track_for(P) == D. Identity when shuffle is off.
    sweep_resolver = (lambda t: t) if shuffle_active else reward_track_for
    dest_to_phys = {}
    dest_to_phys_real = {}
    for _p in HUB_STATIC:
        dest_to_phys.setdefault(sweep_resolver(_p), _p)
        dest_to_phys_real.setdefault(reward_track_for(_p), _p)

    inv = Inv()
    collected = set()
    _reachable_pads_and_collect(
        inv, exits, locations, pad_reqs, stage2_reqs, collected, start)

    remaining_pads = sorted(t for t in HUB_STATIC if t not in pad_reqs)

    def _stage2_pending():
        # A trophy dest track whose Trophy Race is collected but whose stage 2 is
        # not yet assigned. (All trophy races become collectable once every pad has
        # a satisfiable stage 1, so this drains to empty.)
        return any(
            d not in stage2_reqs and f"{d}: Trophy Race" in collected
            for d in TROPHY_TRACKS
        )

    # 2) sphere loop: assign stage-1 reqs to every pad AND stage-2 reqs to every
    # trophy pad once its trophy race is reachable.
    # world.json-derived Key geography for the fallback's cheapest-first sort
    # (never HUB_STATIC, whose values are a heuristic that can drift from the
    # live geography).
    keygate = _pad_keygate_table(crystals_at_hub_floor=_crystals_open(world))
    guard = 0
    max_iter = len(HUB_STATIC) * 16 + 128
    s2_real_count = 0  # how many REAL (non-collapsed) stage-2 gates assigned so far
    s2_collapsed = set()  # dest tracks whose stage 2 collapsed to a stage-1 echo
    while remaining_pads or _stage2_pending():
        guard += 1
        if guard > max_iter:
            raise RuntimeError("CTR warp-pad sphere-search failed to converge")

        open_unassigned = _reachable_pads_and_collect(
            inv, exits, locations, pad_reqs, stage2_reqs, collected, start)

        # 2a) assign stage 2 for any trophy dest track now reachable (its Trophy
        # Race collected) but still unassigned. Draw from the current inventory --
        # which excludes that pad's own still-locked relics/tokens. OPEN model: a
        # real tier-2 requirement is the DEFAULT; the relaxation fallbacks below
        # only collapse a pad's tier 2 to its tier 1 when needed.
        for dest in sorted(TROPHY_TRACKS):
            if dest in stage2_reqs:
                continue
            if f"{dest}: Trophy Race" in collected:
                s2 = _assign_stage2_from_inv(rnd, inv, allowed)
                # Collapse this pad's tier 2 to its tier 1 (satisfiable the instant
                # the trophy race is reached -> no extra gate, no reward pinning)
                # when ANY of:
                #  (a) nothing ownable backs a real tier 2 (hard golden-path guard);
                #  (b) we have already placed _STAGE2_REAL_CAP real gates this seed --
                #      a DETERMINISTIC cap on the number of distinct stage-2 gates AP
                #      fill must satisfy. Trophy pads open in sphere order, so the cap
                #      keeps real tier-2 gates on the EARLY pads (which fill orders
                #      comfortably) and collapses the late ones (the fill-capacity
                #      tail). The cap is well above a typical seed's real-gate count,
                #      so two-stage stays the DEFAULT experience on ordinary seeds and
                #      only the densest, latest pads collapse;
                #  (c) the baseline relief-valve roll fires (adds per-seed variety to
                #      WHICH late pads collapse).
                phys = dest_to_phys.get(dest, dest)
                if (s2 is None
                        or s2_real_count >= _STAGE2_REAL_CAP
                        or rnd.randrange(100) < _STAGE2_COLLAPSE_CHANCE):
                    s2 = pad_reqs.get(phys)
                    s2_collapsed.add(dest)
                else:
                    s2_real_count += 1
                    _note_assigned_requirement(s2)
                stage2_reqs[dest] = s2
        # re-collect: a just-opened stage 2 may add relics/tokens to inventory.
        open_unassigned = _reachable_pads_and_collect(
            inv, exits, locations, pad_reqs, stage2_reqs, collected, start)

        # 2b) assign stage 1 to one reachable unassigned pad (unchanged logic).
        if remaining_pads:
            reachable = sorted(t for t in remaining_pads if t in open_unassigned)
            if not reachable:
                # No statically-reachable unassigned pad. Assign the cheapest-Key
                # pad a minimal requirement so the graph can open further (rare
                # residual case; counts stay satisfiable since _assign_from_inv only
                # ever picks currently-owned item types).
                reachable = sorted(
                    remaining_pads,
                    key=lambda t: (keygate.get(_pad_exit_name(t), 0), t))[:1]
            track = rnd.choice(reachable)
            pad_reqs[track] = _assign_from_inv(rnd, inv, allowed)
            _note_assigned_requirement(pad_reqs[track])
            remaining_pads.remove(track)
            _reachable_pads_and_collect(
                inv, exits, locations, pad_reqs, stage2_reqs, collected, start)

    # 3) post-pass (ports lines 465-510), over a sorted copy. Only LOWERS counts,
    # so it cannot break the solvable DAG built above. Applied to both stages.
    # Stage 2 additionally gets a hard count CEILING: a tier-2 gate of "14 trophies"
    # or "8 platinum relics" both plays badly (it is barely a second stage, just a
    # near-endgame wall) AND is the dominant fill_restrictive killer in maximally
    # tight seeds (it forces almost the whole pool to be seated before that one
    # location opens). Capping tier-2 counts keeps a real, distinct second stage
    # while leaving fill enough ordering freedom. Counts only ever drop, so the
    # solvable-by-construction DAG is preserved.
    _post_process(rnd, pad_reqs, mode, count_ceiling=_STAGE1_COUNT_CEILING)
    _post_process(rnd, stage2_reqs, mode, count_ceiling=_STAGE2_COUNT_CEILING)

    # 3b) RE-VALIDATION against the actual shuffled graph (only when the DAG was
    # built on the identity view). First re-key every COLLAPSED stage 2 to its
    # REAL host pad's final stage-1: a collapse means "no gate beyond the trophy
    # race", and only the value of the pad that actually HOSTS the destination
    # preserves that meaning post-shuffle. Then sweep the shuffled graph and
    # relax only the requirements that fail there.
    if shuffle_active:
        for _dest in s2_collapsed:
            if _dest in stage2_reqs:
                stage2_reqs[_dest] = pad_reqs.get(
                    dest_to_phys_real.get(_dest, _dest))
        # Item types real fill CANNOT relocate this seed: their placement is
        # pinned to vanilla sources, so the synthetic sweep's model of them is
        # AUTHORITATIVE (a pinned-type requirement the sweep cannot validate may
        # be genuinely circular -- e.g. a gem gate on the path to the cups that
        # hold every gem). Pool-shuffled types (trophies, tokens, shuffled
        # keys/gems, slider-100 relics) stay lenient: fill seats them freely.
        _o = world.options
        pinned_items = set()
        if int(_o.goal.value) == 4 or not bool(_o.shuffle_gems.value):
            pinned_items.update(GEM_ITEMS)   # allgemcups always pins the gems
            pinned_items.add("AnyGem")
        if not bool(_o.shuffle_keys.value):
            pinned_items.add("Key")
        # Regions holding PINNED GOAL-PROGRESSION locations: under the
        # all-gem-cups goal the 5 Gems are pinned at their cups AND completing
        # every cup IS the goal, so the accessibility check hard-requires each
        # cup region reachable. The sweep must therefore prove the whole chain
        # to every cup; requirements it cannot validate on that chain get
        # relaxed regardless of item type. (Other pinned classes need no
        # region rule: boss-race regions sit behind static trophy doors only,
        # never behind pad requirements, and non-goal pinned gems' regions are
        # only location-reachability under accessibility:full, which pool-item
        # fill bridges -- 0 failures observed at the 14k scale.)
        critical_regions = frozenset(
            f"{c} Gem Cup" for c in ("Red", "Green", "Blue", "Yellow", "Purple")
        ) if int(_o.goal.value) == 4 else frozenset()
        relaxed_s1, relaxed_s2 = _revalidate_against_shuffle(
            rnd, exits_real, locations_real, pad_reqs, stage2_reqs,
            dest_to_phys_real, start, allowed, keygate,
            frozenset(pinned_items), critical_regions)
        world._ctr_s2_relaxed_s1 = relaxed_s1
        world._ctr_s2_relaxed_s2 = relaxed_s2

    # 4) assemble {track: {1: stage1, 2: stage2}}. Stage-2 eligibility keys off the
    # DESTINATION (contract §2/§4, design §3): a physical pad carries a meaningful
    # stage 2 iff the track it LOADS (reward_track_for) is one of the 16 trophy
    # tracks -- NOT iff the physical pad itself is a trophy pad. Under merged
    # destination shuffle a trial / cup / crystal physical pad may host a trophy
    # track (-> real stage 2), and a trophy physical pad may host non-race content
    # (-> no stage 2). stage2_reqs is dest-track keyed, so the lookup is by dest.
    out = {}
    for t in HUB_STATIC:
        dest = reward_track_for(t)
        s2 = stage2_reqs.get(dest) if dest in TROPHY_TRACKS else None
        out[t] = {1: pad_reqs.get(t), 2: s2}
    return out


# --------------------------------------------------------------------------
# SPHERE-0 BREADTH REPAIR
#
# WHY THIS EXISTS
# ---------------
# CTR generation used to fail with AP's FillError on roughly 0.3% of seeds in a
# multiworld. The DAG _run_sphere_search_once produces is always SOLVABLE by
# construction (every requirement is drawn from an inventory owned strictly
# before that gate opens), so the seed is never logically impossible. What fails
# is fill_restrictive's greedy placement: CTR's item pool is ~98% progression in
# every config, so when sphere 0 opens only a handful of locations there is
# nowhere to seat the early progression that would open the next pads, and fill
# runs out of reachable slots for the last progression items.
#
# The lever is how WIDE sphere 0 is -- how many locations are open at zero items
# once the free-pad subset and the stage-1/stage-2 gates are decided. Measured
# over 10,000 default-config + Empty-companion seeds, failures vs sphere-0
# breadth (_sphere0_breadth above):
#
#     breadth   1      2       3        4      5      6+
#     fails   0/25   4/169   27/230   0/15   0/43   0/9518
#
# Every failure sat at breadth 2 or 3. Breadth >= 4 produced ZERO failures over
# ~19.5k samples. So instead of widening the floor for everyone, we simply
# re-roll the sphere search on the seeds that landed narrow, and keep the first
# roll that clears the threshold. Measured over seeds 0-9999: baseline 31
# failures, this repair 3.
#
# WHY NOT JUST RAISE _FREE_MIN
# ----------------------------
# _FREE_MIN = 5 also drops to ~1 failure, but it destroys starting-pad variety:
# 100% of seeds would open with 5 free pads, versus ~70% getting 3 today. The
# re-roll preserves the distribution (68.8% of seeds still get 3 free pads) and
# fires on only ~4.2% of seeds. _FREE_MIN stays at 3.
#
# THIS IS NOT A COMPLETE FIX -- DO NOT READ IT AS ONE
# ---------------------------------------------------
# The residual is ~3 failures per 10k, and that is ACCEPTED and documented as a
# known issue. The seeds that still fail are GEOGRAPHY-CAPPED: on those, no
# choice of free-pad subset can widen sphere 0 past the threshold, because the
# locations behind the openable pads simply are not there. Re-rolling more times
# does not help them -- hence the bounded attempt count and the last-resort
# stage-2 collapse below (which measured 1 failure per 10k but changes the
# played experience by dropping every second-stage gate, so it only fires when
# the seed would otherwise be left narrow).
#
# Future maintainers: if you want to push this further, the remaining tail is
# not a tuning problem in this function. It is either an AP fill ordering
# concern or a question of adding sphere-0 location capacity to the geography.
# --------------------------------------------------------------------------

# Minimum sphere-0 breadth we re-roll toward. 4 is the measured zero-failure
# floor (see the table above); it is not a round number, do not "tidy" it.
_SPHERE0_MIN_BREADTH = 4
# Bounded re-roll budget. ~4.2% of seeds enter the loop at all and nearly all of
# those clear on the first or second retry; the cap exists so a geography-capped
# seed cannot spin. Each attempt costs one extra build_graph.
_SPHERE0_REPAIR_TRIES = 8


def run_sphere_search(world, mode, reward_track_for=None,
                      collapse_stage2=False, include_gem_cups=False):
    """Sphere search with the sphere-0 breadth repair. Same signature and return
    shape as _run_sphere_search_once; see the comment block above for why.

    Deterministic on world.random: every attempt consumes RNG from the same
    stream, and _sphere0_breadth consumes none, so a given seed always produces
    the same result.
    """
    rtf = reward_track_for or (lambda t: t)
    best, best_b = None, -1
    for _ in range(_SPHERE0_REPAIR_TRIES):
        out = _run_sphere_search_once(world, mode, reward_track_for,
                                      collapse_stage2, include_gem_cups)
        b = _sphere0_breadth(world, out, rtf, include_gem_cups)
        if b > best_b:
            best, best_b = out, b
        if b >= _SPHERE0_MIN_BREADTH:
            return out
    if not collapse_stage2:
        # Geography-capped seed: no free-pad subset widens sphere 0. Last resort
        # -- drop every stage-2 gate for this seed, which frees the TT / token
        # locations on every reachable trophy race into sphere 0. Costs this
        # seed its two-stage experience, but it is the difference between a
        # playable seed and a FillError. Assigning _ctr_two_stage_active here is
        # safe: Regions.create_regions sets it BEFORE calling us, so this False
        # sticks and __init__ correctly skips the two-stage fill probe.
        world._ctr_two_stage_active = False
        return _run_sphere_search_once(world, mode, reward_track_for,
                                       True, include_gem_cups)
    return best


def _revalidate_against_shuffle(rnd, exits, locations, pad_reqs, stage2_reqs,
                                dest_to_phys, start, allowed, keygate,
                                pinned_items=frozenset(),
                                critical_regions=frozenset()):
    """Verify the identity-topology requirement DAG against the ACTUAL shuffled
    graph; relax ONLY the requirements that fail there.

    Sweeps the shuffled graph to a fixed point with all assigned requirements
    enforced (_reachable_pads_and_collect). A stage-1 requirement FAILS when its
    pad sits at the sweep frontier (host region reached, static hub gate passed)
    but the requirement is unsatisfiable from everything collectable before the
    pad opens. A stage-2 requirement FAILS when its destination's Trophy Race is
    collected but the gate is unsatisfiable from the final inventory. A failed
    stage 1 is re-drawn from the inventory actually collectable at that point
    (satisfiable by construction, the sweep's own assignment rule, stage-1 count
    ceiling applied); a failed stage 2 collapses to its REAL host pad's stage-1
    (= no gate beyond the trophy race).

    Pads the synthetic sweep cannot REACH at the fixed point (content starvation
    behind a static boss/key gate) are NOT relaxed as long as their requirement
    demands a POOL-SHUFFLED item type: the synthetic vanilla-reward inventory
    under-approximates real fill, which places pool items freely on reachable
    locations, so unreached-ness is not evidence of an unsatisfiable
    requirement. True fill risk stays covered downstream by the pre_fill probe
    backstop, the accessibility sweep, and the fuzz gate.

    The EXCEPTION is `pinned_items`: item types whose placement is pinned to
    their vanilla sources this seed (gems under the all-gem-cups goal or
    shuffle_gems off; Keys under shuffle_keys off). Fill cannot relocate those,
    so the sweep's model of them is authoritative, and a pinned-type
    requirement the sweep never validated (unreached pad / uncollected trophy
    dest) may be genuinely circular -- e.g. a gem gate between the start and
    the cups that hold every gem makes an all-gem-cups seed unbeatable. Those
    are relaxed too.

    `critical_regions` are regions holding pinned GOAL-progression locations
    (the 5 gem cups under the all-gem-cups goal): while any of them is
    unreached at the fixed point, unvalidated requirements keep being relaxed
    (cheapest key floor first, ANY item type) until the sweep proves the chain
    or only static gates (pool-bridgeable trophy/key doors) remain in the way.

    Bounded: relaxation is monotone (a weakened requirement only ever opens more
    of the graph, and the fixed-point inventory can only grow between
    iterations), each pad/dest relaxes at most once, one relaxation per sweep.
    Returns ({track: (old, new)}, {dest: (old, new)}) for the relaxations."""
    relaxed_s1 = {}
    relaxed_s2 = {}
    pad_exit_to_track = {_pad_exit_name(t): t for t in HUB_STATIC}
    guard = 0
    while True:
        guard += 1
        if guard > len(HUB_STATIC) + len(TROPHY_TRACKS) + 8:
            raise RuntimeError("CTR stage-2 re-validation failed to converge")
        inv = Inv()
        collected = set()
        _reachable_pads_and_collect(
            inv, exits, locations, pad_reqs, stage2_reqs, collected, start)

        def _passes(reqs):
            return all(inv.count(i) >= c for i, c in reqs)

        # Frontier scan under the final inventory: which assigned pads are
        # reachable-but-closed purely because of their own stage-1 requirement?
        seen = {start}
        frontier = [start]
        blocked_s1 = []
        while frontier:
            cur = frontier.pop()
            for exit_name, tgt, gate in exits.get(cur, []):
                if not _passes(gate):
                    continue
                track = pad_exit_to_track.get(exit_name)
                if track is not None:
                    req = pad_reqs.get(track)
                    if req is not None and not _passes([req]):
                        # Blocked-ness must be evaluated BEFORE the BFS dedup:
                        # destination regions carry ungated return exits to
                        # their VANILLA hubs, so a pad's target being reachable
                        # through another path must not hide that this pad's
                        # own requirement is unsatisfiable.
                        if track not in relaxed_s1 and track not in blocked_s1:
                            blocked_s1.append(track)
                        continue
                if tgt in seen:
                    continue
                seen.add(tgt)
                frontier.append(tgt)

        if blocked_s1:
            track = min(blocked_s1,
                        key=lambda t: (keygate.get(_pad_exit_name(t), 0), t))
            new = _assign_from_inv(rnd, inv, allowed)
            if (new is not None and new[0] != "Key"
                    and new[1] > _STAGE1_COUNT_CEILING):
                new = (new[0], _STAGE1_COUNT_CEILING)
            relaxed_s1[track] = (pad_reqs.get(track), new)
            pad_reqs[track] = new
            continue

        blocked_s2 = sorted(
            dest for dest, s2 in stage2_reqs.items()
            if s2 is not None and dest not in relaxed_s2
            and f"{dest}: Trophy Race" in collected and not _passes([s2]))
        if blocked_s2:
            dest = blocked_s2[0]
            phys = dest_to_phys.get(dest, dest)
            relaxed_s2[dest] = (stage2_reqs.get(dest), pad_reqs.get(phys))
            stage2_reqs[dest] = pad_reqs.get(phys)
            continue

        # "Proven-open": the sweep actually validated this pad at the fixed
        # point -- host reachable, static gate passed, requirement met. Only a
        # proven-open pad's requirement is known-satisfiable post-shuffle;
        # everything else is unvalidated (a merely-reachable host is NOT enough:
        # destination regions' ungated vanilla-hub return exits leak hubs into
        # reachability, and a pad behind a failed static Key gate never had its
        # requirement exercised at all).
        pad_host = {}
        pad_gate = {}
        for region, ex_list in exits.items():
            for exit_name, _tgt, _gate in ex_list:
                track = pad_exit_to_track.get(exit_name)
                if track is not None:
                    pad_host[track] = region
                    pad_gate[track] = _gate

        def _proven_open(t):
            if pad_host.get(t) not in seen:
                return False
            if not _passes(pad_gate.get(t, [])):
                return False
            req = pad_reqs.get(t)
            return req is None or _passes([req])

        # Pinned-item completeness (see docstring): a requirement the sweep
        # never validated may not demand a pinned type.
        if pinned_items:
            pinned_s1 = sorted(
                t for t, req in pad_reqs.items()
                if req is not None and t not in relaxed_s1
                and req[0] in pinned_items
                and not _proven_open(t))
            if pinned_s1:
                track = min(pinned_s1,
                            key=lambda t: (keygate.get(_pad_exit_name(t), 0), t))
                new_req = _assign_from_inv(rnd, inv, allowed)
                if (new_req is not None and new_req[0] != "Key"
                        and new_req[1] > _STAGE1_COUNT_CEILING):
                    new_req = (new_req[0], _STAGE1_COUNT_CEILING)
                relaxed_s1[track] = (pad_reqs.get(track), new_req)
                pad_reqs[track] = new_req
                continue
            pinned_s2 = sorted(
                dest for dest, s2 in stage2_reqs.items()
                if s2 is not None and dest not in relaxed_s2
                and s2[0] in pinned_items
                and f"{dest}: Trophy Race" not in collected)
            if pinned_s2:
                dest = pinned_s2[0]
                phys = dest_to_phys.get(dest, dest)
                relaxed_s2[dest] = (stage2_reqs.get(dest), pad_reqs.get(phys))
                stage2_reqs[dest] = pad_reqs.get(phys)
                continue

        # Critical-region completeness (see docstring): while a region holding
        # a pinned goal-progression location is unreached, keep relaxing
        # unvalidated requirements (any type). When none remain, only static
        # gates (pool-bridgeable trophy/key doors) block the path -- stop.
        if critical_regions and not critical_regions <= seen:
            unvalidated = sorted(
                t for t, req in pad_reqs.items()
                if req is not None and t not in relaxed_s1
                and not _proven_open(t))
            if unvalidated:
                track = min(unvalidated,
                            key=lambda t: (keygate.get(_pad_exit_name(t), 0), t))
                new_req = _assign_from_inv(rnd, inv, allowed)
                if (new_req is not None and new_req[0] != "Key"
                        and new_req[1] > _STAGE1_COUNT_CEILING):
                    new_req = (new_req[0], _STAGE1_COUNT_CEILING)
                relaxed_s1[track] = (pad_reqs.get(track), new_req)
                pad_reqs[track] = new_req
                continue
        break
    return relaxed_s1, relaxed_s2


def _post_process(rnd, pad_reqs, mode, count_ceiling=None):
    """66% lower count *0.6 ceil (when count != 0); else if mode==2 and req is
    ('Key',4) -> ('Key',3). Iterate a SORTED copy for determinism. When
    count_ceiling is given (stage 2), clamp the final count to it AFTER the random
    reduction -- a pure LOWERING, so the solvable DAG is preserved (Key counts are
    left uncapped: a Key gate maxes at 4 and is cheap to satisfy)."""
    for track in sorted(pad_reqs):
        req = pad_reqs[track]
        if req is None:
            continue
        item, cnt = req
        if rnd.randrange(100) < 66:
            if cnt != 0:
                cnt = max(1, math.ceil(cnt * 0.6))
                pad_reqs[track] = (item, cnt)
        elif mode == 2 and item == "Key" and cnt == 4:
            pad_reqs[track] = ("Key", 3)
            cnt = 3
        if count_ceiling is not None and item != "Key" and cnt > count_ceiling:
            pad_reqs[track] = (item, count_ceiling)


# ---------------------------------------------------------------------------
# Map sphere output -> slot_data {type,count,colour} contract
# ---------------------------------------------------------------------------

_COLOURS = ["Red", "Green", "Blue", "Yellow", "Purple"]
# Relic tiers ride the SAME colour field as token/gem colours (design ruling
# 2026-07-08): 0 = Sapphire, 1 = Gold, 2 = Platinum. Tiers are INDEPENDENT items
# (a Gold req is met ONLY by Gold Relic -- no downward hierarchy), so the concrete
# tier must survive the wire; dropping it to colour -1 silently rewrote every
# stage-1 relic gate to Sapphire (the pre-schema-4 bug).
_RELIC_TIERS = ["Sapphire", "Gold", "Platinum"]


def to_slot_req(req):
    """(item, count) | None -> {type,count,colour}.

    type: 0 none / 1 trophies / 2 keys / 3 tokens / 4 relic / 5 gems /
          6 AnyToken / 7 AnyRelic / 8 AnyGem (colour -1, native sums the whole type).
    colour 0..4 = R,G,B,Y,P for token/gem; 0..2 = Sapphire,Gold,Platinum for the
    type-4 relic tier (schema_version 4); -1 otherwise. Under requirement_specificity
    = specific_colour, Any* are flattened to a concrete colour upstream (_resolve_any)
    so only type 1-5 reach here. Under any_of (default) the Any* aggregates survive
    and emit type 6/7/8 with colour -1.

    A free bootstrap pad (req None) is emitted as an EXPLICIT "0 trophies"
    requirement (type 1, count 0) rather than type 0. type 0 makes native fall
    back to the pad's VANILLA numTrophiesToOpen floor (ap_hooks.c), which would
    re-inject the deterministic vanilla trophy spine; "0 trophies" is always
    satisfied, so the bootstrap pad is genuinely open at spawn and the randomizer
    owns every entry requirement. (Vanilla unlock mode never calls this, so it
    keeps its real floors.)"""
    if req is None:
        return {"type": 1, "count": 0, "colour": -1}
    item, cnt = req
    cnt = int(cnt)
    if item == "AnyCtrToken":
        return {"type": 6, "count": cnt, "colour": -1}
    if item == "AnyRelic":
        return {"type": 7, "count": cnt, "colour": -1}
    if item == "AnyGem":
        return {"type": 8, "count": cnt, "colour": -1}
    if item == "Trophy":
        return {"type": 1, "count": cnt, "colour": -1}
    if item == "Key":
        return {"type": 2, "count": cnt, "colour": -1}
    if item.endswith("CTR Token"):
        return {"type": 3, "count": cnt, "colour": _COLOURS.index(item.split()[0])}
    if item.endswith("Relic"):
        return {"type": 4, "count": cnt, "colour": _RELIC_TIERS.index(item.split()[0])}
    if item.endswith("Gem"):
        return {"type": 5, "count": cnt, "colour": _COLOURS.index(item.split()[0])}
    raise ValueError(f"unmappable warp-pad requirement item: {item!r}")


# ---------------------------------------------------------------------------
# Destination shuffle -- non-identity warp_pad_map
# ---------------------------------------------------------------------------

# Destination-shuffle CATEGORY POOLS (slot_data v3). A category
# is a set of physical pad LevelIDs whose destinations may be permuted. Which
# categories participate is chosen by warp_pad_shuffle_categories, whether they
# cross-shuffle by warp_pad_shuffle_grouping, and cups/crystals additionally need
# their include_* content option (see resolve_shuffle_pools). LevelIDs from
# warp_pad_ids.json.
#   tracks   = the 16 trophy-race pads + the 2 trials (16 Slide Coliseum, 17 Turbo
#              Track). Trials ride in tracks (they carry race-track-style content,
#              so they shuffle with the races); native dispatch handles a trophy race on a
#              trial pad and vice versa under the v3 build.
#   crystals = the 4 battle-arena pads.
#   cups     = the 5 gem-cup pads (LevelIDs 100-104).
CATEGORY_POOLS = {
    "tracks": [3, 6, 9, 8, 14, 4, 5, 0, 2, 1, 12, 15, 7, 10, 11, 13, 16, 17],
    "crystals": [21, 19, 23, 18],
    "cups": [100, 101, 102, 103, 104],
}

# The vanilla-unlock collapse's 'races only' subset of tracks: the 16 trophy-race
# pads WITHOUT the two trials (legacy same-category behaviour, matching the old
# SHUFFLE_GROUPS['race']). Used only when warppad_unlock_requirements == vanilla.
_LEGACY_RACE_IDS = [3, 6, 9, 8, 14, 4, 5, 0, 2, 1, 12, 15, 7, 10, 11, 13]


def resolve_shuffle_pools(world):
    """Resolve which pad-ID pools take part in destination shuffle, and how, from
    warp_pad_shuffle_categories × warp_pad_shuffle_grouping × the include_* content
    filters × the vanilla-unlock collapse (design §1).

    Returns (pools, grouping) where `pools` is a list of ID-lists to permute
    independently (one list under merged; one per category under per_category) and
    `grouping` is the effective grouping string. An empty `pools` means no shuffle
    (identity map).

    Participation: a category participates iff selected AND its content is in the
    seed -- `cups` needs include_gem_cups, `crystals` needs include_battle_arenas,
    `tracks` is always in the seed.

    Vanilla-unlock collapse: when warppad_unlock_requirements == vanilla (0), the
    grouping is forced to per_category, cups/trials are excluded, and `tracks`
    degrades to races-only (_LEGACY_RACE_IDS) -- regardless of the yaml. Native
    vanilla gate enforcement + the entrance-keyed vanilla trophy floor
    (Rules.add_vanilla_floor_rules, issue #80) are only defined for the race<->race
    matrix, so cross-category / cup / trial shuffle require a randomized unlock mode.
    Category SELECTION is still honoured (an unselected category never shuffles, even
    in the collapse)."""
    opts = world.options
    cats = set(getattr(opts, "warp_pad_shuffle_categories").value)
    grouping = getattr(opts, "warp_pad_shuffle_grouping").current_key  # merged/per_category
    unlock_mode = opts.warppad_unlock_requirements.value
    inc_arenas = bool(opts.include_battle_arenas.value)
    inc_cups = bool(opts.include_gem_cups.value)

    if unlock_mode == 0:
        # LEGACY collapse: races-only + crystals, per_category, no cups/trials.
        pools = []
        if "tracks" in cats:
            pools.append(list(_LEGACY_RACE_IDS))
        if "crystals" in cats and inc_arenas:
            pools.append(list(CATEGORY_POOLS["crystals"]))
        return pools, "per_category"

    # Randomized unlock modes: full category machinery.
    participating = []
    if "tracks" in cats:
        participating.append(list(CATEGORY_POOLS["tracks"]))
    if "crystals" in cats and inc_arenas:
        participating.append(list(CATEGORY_POOLS["crystals"]))
    if "cups" in cats and inc_cups:
        participating.append(list(CATEGORY_POOLS["cups"]))

    if grouping == "merged":
        union = [lid for pool in participating for lid in pool]
        return ([union] if union else []), "merged"
    return participating, "per_category"


# ---------------------------------------------------------------------------
# Per-tier trophy-capacity invariant (merged + gem-cups + keys-off starvation fix)
# ---------------------------------------------------------------------------
#
# Under `merged` destination shuffle with `shuffle_keys: false`, the shuffle can
# drop too many ZERO-capacity destinations (gem cups whose Gem is lock-placed when
# gems are not shuffled) onto the pads reachable before a boss floor, leaving fewer
# trophy-CAPABLE (reachable, non-pre-placed) locations than that boss's fixed trophy
# gate (4/8/12/16) needs -> fill_restrictive dead-ends (FillError). Keys-off is the
# trigger because the first Key only drops after Ripper Roo (4 Trophies), so those
# 4 Trophies MUST be seatable in the pre-first-key sphere; keys-on floods that
# frontier with an early Key and never starves. The counting rule below was
# validated on repro seed 509876816.
#
# We enforce a per-boss-floor capacity floor by a bounded re-roll of the destination
# permutation (same world.random stream as the existing 8x identity re-roll; RNG is
# consumed ONLY when a floor is breached, so a map that already satisfies every floor
# generates byte-identically). The count is a STAGE-2-INDEPENDENT lower bound on the
# real trophy-capable capacity: a race destination contributes only its Trophy Race
# (+ podium rungs) because its Time Trial / CTR-token slots sit behind a stage-2 gate
# that may hold them back pre-key (B1: "race TTs/tokens = 0 capacity pre-key"). The
# bound is SOUND -- real capacity >= this count -- so a map that PASSES is genuinely
# fillable at those floors and is never re-rolled; only maps at or below the bound
# (which include every genuine starvation map) are repaired.

# (trophy floor, boss keys already earned). Keys come only from bosses when
# shuffle_keys is off: 0 before Ripper Roo, 1 before Papu, etc. A physical pad is
# reachable at a floor iff its hub Key gate <= that floor's key count. Mirrors
# Regions.BOSS_TROPHY + the world.json hub Key graph (verified equal to B1's tiers:
# 4 pads @0 keys, 11 @1, 21 @2, 26 @3).
_BOSS_CAP_FLOORS = ((4, 0), (8, 1), (12, 2), (16, 3))

# Bounded re-roll budget before the constructive fallback. Only 5 of 27 merged-pool
# destinations are ever zero-capacity (the gem cups), so a satisfying permutation is
# dense in the sample space and a breach is cleared in far fewer draws in practice;
# the budget is generous insurance, not an expected cost.
_CAPACITY_MAX_REROLLS = 16

_KEYGATE_CACHE = {}

# The 4 crystal/battle-arena pad exits whose vanilla "+1 Key" gate is stripped
# to the hub floor in randomized mode with include_battle_arenas ON
# (Regions.create_regions, the open-when-free model).
_CRYSTAL_PAD_EXIT_NAMES = frozenset({
    "Skull Rock Warp Pad", "Rampage Ruins Warp Pad",
    "Rocky Road Warp Pad", "Nitro Court Warp Pad",
})


def _pad_keygate_table(crystals_at_hub_floor=False):
    """{pad_exit_name -> minimum boss Keys required to REACH that physical pad's
    warp-pad exit}, derived from the static hub Key graph in data/world.json.

    Keys are monotonic and hub gates nest, so the min keys to reach a region is the
    minimax over paths of the largest has('Key', N) gate crossed; a pad's key floor
    is then max(region floor, the pad-exit's own Key gate). This is the PHYSICAL-pad
    reachability the capacity sweep keys off -- a destination's OWN hub gate is
    bypassed by the exit rewire (Regions.create_regions), so only the physical pad's
    gate matters.

    crystals_at_hub_floor: pass True when the seed strips the crystal pads' vanilla
    "+1 Key" gates (randomized unlock + include_battle_arenas, Regions.create_regions);
    the 4 crystal pad exits then sit at their host hub's floor (Skull Rock 0, Rampage
    Ruins 1, Rocky Road 2, Nitro Court 3). This function reads the PRISTINE world.json
    from disk, NOT the per-seed mutated copy, so the strip must be mirrored here
    explicitly -- it does NOT follow automatically. Static per variant -> cached."""
    global _KEYGATE_CACHE
    cached = _KEYGATE_CACHE.get(bool(crystals_at_hub_floor))
    if cached is not None:
        return cached
    data = json.loads(
        pkgutil.get_data(__package__, "data/world.json").decode("utf-8"))
    pads = json.loads(
        pkgutil.get_data(__package__, "data/warp_pad_ids.json").decode("utf-8"))["pads"]
    regions = {r["name"]: r for r in data["regions"]}
    start = next(r["name"] for r in data["regions"] if r.get("is_start"))

    def key_req(text):
        return max((int(n) for n in re.findall(r"has\('Key',\s*(\d+)\)", text or "")),
                   default=0)

    # minimax key distance from the start region.
    dist = {start: 0}
    pq = [(0, start)]
    while pq:
        dk, cur = heapq.heappop(pq)
        if dk > dist.get(cur, 1 << 30):
            continue
        for ex in regions.get(cur, {}).get("exits", []):
            tgt = ex.get("target")
            if tgt is None or tgt not in regions:
                continue
            nk = max(dk, key_req(ex.get("access_rule", "True")))
            if nk < dist.get(tgt, 1 << 30):
                dist[tgt] = nk
                heapq.heappush(pq, (nk, tgt))

    # host region + own access rule per pad exit.
    exit_host = {}
    for r in data["regions"]:
        for ex in r.get("exits", []):
            if ex["name"] in pads:
                exit_host[ex["name"]] = (r["name"], ex.get("access_rule", "True"))
    table = {}
    for pad_name in pads:
        host, ar = exit_host.get(pad_name, (start, "True"))
        if crystals_at_hub_floor and pad_name in _CRYSTAL_PAD_EXIT_NAMES:
            # Stripped seed: the pad-exit's own vanilla "+1 Key" gate is gone;
            # only the host hub's floor gates it.
            table[pad_name] = dist.get(host, 1 << 30)
        else:
            table[pad_name] = max(dist.get(host, 1 << 30), key_req(ar))
    _KEYGATE_CACHE[bool(crystals_at_hub_floor)] = table
    return table


def _capacity_context(world):
    """Per-seed inputs to the trophy-capacity count that do not depend on the map:
    podium rung count, guaranteed-unpinned relic-trial tiers, and whether gem-cup
    Gem locations are lock-placed (0 capacity)."""
    o = world.options
    # Podium rungs created per trophy race (0 when the feature is off); the new
    # 5-rung superset count comes straight from the shared creation-subset helper.
    from .podium import created_rung_keys_from_options
    podium = len(created_rung_keys_from_options(o))
    # A relic Time Trial location is a guaranteed (un-pinnable) fillable slot only at
    # slider 100; below 100 it may be pinned to its vanilla relic (0 capacity), so the
    # sound lower bound counts only the fully-open tiers.
    sliders = (o.sapphire_relic_progression.value,
               o.gold_relic_progression.value,
               o.platinum_relic_progression.value)
    trial_tiers = sum(1 for s in sliders if s >= 100)
    # Gem-cup Gem is lock-placed when gems are not shuffled, or always for the
    # all-gem-cups goal (Goal.option_allgemcups == 4). Locked -> 0 trophy capacity.
    gem_locked = (not bool(o.shuffle_gems.value)) or (o.goal.value == 4)
    return {"podium": podium, "trial_tiers": trial_tiers, "gem_locked": gem_locked}


def _dest_trophy_capacity(dest_lid, id_kind, ctx):
    """Stage-2-independent lower bound on the trophy-CAPABLE fillable locations a
    destination LevelID exposes once its (physical) pad is reached:
      race    -> 1 Trophy Race + podium rungs (TTs/token excluded: stage-2-gated)
      crystal -> 1 Crystal Bonus Round
      trial   -> guaranteed-unpinned relic Time Trials (single-stage, no stage-2 gate)
      cup     -> 1, or 0 when its Gem is lock-placed (gems-off / all-gem-cups goal)."""
    kind = id_kind.get(dest_lid)
    if kind == "race":
        return 1 + ctx["podium"]
    if kind == "crystal":
        return 1
    if kind == "trial":
        return ctx["trial_tiers"]
    if kind == "cup":
        return 0 if ctx["gem_locked"] else 1
    return 0


def _floors_satisfied(out, keygate, id_kind, own_lid, ctx):
    """True iff every boss floor's reachable pads expose >= that floor's trophy count
    of trophy-capable slots. `out` = {pad_exit_name -> dest_levelID} (partial; an
    unshuffled pad loads itself)."""
    for floor, keys in _BOSS_CAP_FLOORS:
        cap = 0
        for pad_name, lid in own_lid.items():
            if keygate.get(pad_name, 0) > keys:
                continue
            cap += _dest_trophy_capacity(out.get(pad_name, lid), id_kind, ctx)
        if cap < floor:
            return False
    return True


def _capacity_gate_open(world, grouping):
    """Cheap keys-off + `merged` gate. The invariant is enforced ONLY here: per_category
    keeps every category on its own pads (cups never reach the always-open race pads),
    and keys-on floods the frontier with an early Key -- both are provably unaffected.
    Kept deliberately allocation-free so those (default) paths stay byte-identical to
    pre-fix generation; the heavier capacity work happens only past this gate.

    VANILLA-FLOOR SOUNDNESS (issue #80): the vanilla trophy floors installed by
    Rules.add_vanilla_floor_rules gate each race pad by trophies, which this count
    does NOT model. That is sound today because vanilla mode forces grouping ==
    per_category (resolve_shuffle_pools), so this gate is CLOSED in vanilla mode and
    the re-roll never runs. If vanilla-mode shuffle is ever widened to `merged`
    (past the current race<->race per_category collapse), this counter must also
    account for the per-pad trophy floor before it can be trusted with floors present."""
    return grouping == "merged" and not bool(world.options.shuffle_keys.value)


def _permute_pools(world, pools, id_to_name):
    """Permute destinations within each resolved pool (the historical body of
    build_warp_pad_map): re-roll up to 8x if a pool's whole permutation is identity.
    Returns {pad_exit_name -> destination LevelID}. Uses world.random."""
    rnd = world.random
    out = {}
    for ids in pools:
        if len(ids) < 2:
            continue  # nothing to permute
        perm = ids[:]
        for _ in range(8):
            rnd.shuffle(perm)
            if perm != ids:
                break
        for phys, dest in zip(ids, perm):
            name = id_to_name.get(phys)
            if name is not None:
                out[name] = dest  # pad_exit_name -> destination track LevelID
    return out


def _constructive_capacity_pin(world, pools, id_to_name, keygate, id_kind, own_lid, ctx):
    """Deterministic fallback when the bounded re-roll cannot land a satisfying map
    (astronomically unlikely -- a valid arrangement always exists since only the 5
    cups are zero-capacity). Under `merged` there is exactly one pool; pin race
    destinations onto the always-open (0-key) pads to guarantee the Ripper Roo floor,
    then re-permute the remaining destinations, re-rolling that remainder to satisfy
    the higher floors' wide slack. RNG = world.random."""
    rnd = world.random
    ids = pools[0]  # merged == single pool of LevelIDs
    lid_to_name = {lid: id_to_name.get(lid) for lid in ids}
    open_pos = [i for i, lid in enumerate(ids)
                if keygate.get(lid_to_name.get(lid), 0) == 0]
    race_dests = [lid for lid in ids if id_kind.get(lid) == "race"]

    def _assemble(perm):
        out = {}
        for phys, dest in zip(ids, perm):
            name = id_to_name.get(phys)
            if name is not None:
                out[name] = dest
        return out

    best = None
    for _ in range(_CAPACITY_MAX_REROLLS):
        pinned = list(race_dests)
        rnd.shuffle(pinned)
        perm = [None] * len(ids)
        used = set()
        for pos in open_pos:
            if not pinned:
                break
            d = pinned.pop()
            perm[pos] = d
            used.add(d)
        rest = [lid for lid in ids if lid not in used]
        rnd.shuffle(rest)
        ri = 0
        for pos in range(len(ids)):
            if perm[pos] is None:
                perm[pos] = rest[ri]
                ri += 1
        out = _assemble(perm)
        if best is None:
            best = out  # Ripper Roo floor guaranteed by the race pins above
        if _floors_satisfied(out, keygate, id_kind, own_lid, ctx):
            return out
    return best


def _crystals_open(world):
    """True when this seed strips the crystal pads' vanilla "+1 Key" gates to the
    hub floor (randomized unlock modes + include_battle_arenas ON; the exact gate
    Regions.create_regions applies the strip under)."""
    o = world.options
    return (int(o.warppad_unlock_requirements.value) in (1, 2)
            and bool(o.include_battle_arenas.value))


def build_warp_pad_map(world):
    """{pad_exit_name -> target_track_levelID}. Permutes destinations within each
    resolved pool (resolve_shuffle_pools); re-rolls (up to 8x) if a pool's whole
    permutation is identity. Returns an empty map (identity) when no pool
    participates. Values span the full ID space {0..27, 100..104}: under merged a
    track slot may load a cup/crystal and vice versa.

    Under `merged` + `shuffle_keys: false`, additionally enforces the per-boss-floor
    trophy-capacity invariant (see the block above): a bounded re-roll of the whole
    permutation until every floor has enough trophy-capable slots, else a constructive
    pin. This fires only when a zero-capacity destination participates, and consumes
    NO extra RNG on a map that already satisfies the floors (byte-identical seeds)."""
    id_to_name = {meta["level_id"]: name
                  for name, meta in world.warp_pad_ids.items()}
    pools, grouping = resolve_shuffle_pools(world)
    out = _permute_pools(world, pools, id_to_name)

    # Per-tier trophy-capacity invariant (merged + gem-cups + keys-off starvation).
    # Guarded by the cheap keys-off + merged gate FIRST so the default keys-on and
    # per_category paths allocate nothing new below and stay byte-identical to pre-fix.
    if _capacity_gate_open(world, grouping):
        id_kind = {meta["level_id"]: meta["kind"]
                   for meta in world.warp_pad_ids.values()}
        ctx = _capacity_context(world)
        # Only a zero-capacity destination (a lock-placed gem cup, or a fully-pinned
        # trial) can starve a floor; nothing to enforce when none participates.
        if any(_dest_trophy_capacity(lid, id_kind, ctx) == 0
               for pool in pools for lid in pool):
            keygate = _pad_keygate_table(
                crystals_at_hub_floor=_crystals_open(world))
            own_lid = {name: meta["level_id"]
                       for name, meta in world.warp_pad_ids.items()}
            attempts = 0
            while (not _floors_satisfied(out, keygate, id_kind, own_lid, ctx)
                   and attempts < _CAPACITY_MAX_REROLLS):
                out = _permute_pools(world, pools, id_to_name)
                attempts += 1
            if not _floors_satisfied(out, keygate, id_kind, own_lid, ctx):
                out = _constructive_capacity_pin(
                    world, pools, id_to_name, keygate, id_kind, own_lid, ctx)

    # Comfort guard (Icebound force_vanilla_turbotrack + limit_arena_gemcup_shuffle):
    # when warp-pad unlock requirements are vanilla and gems are not shuffled, the
    # Turbo Track pad keeps its vanilla 5-gem gate, so a Gem Cup / trial destination
    # landing in a trophy pad (or a Gem Cup landing in Turbo Track) would force the
    # tedious tokens -> gem cups -> 5 gems chain. The vanilla-unlock collapse in
    # resolve_shuffle_pools already restricts the pools to races-only + crystals
    # (no trials, no cups) whenever this guard can be active (unlock == vanilla), so
    # the trial/cup pads are never remapped above; this strips any such remap to
    # enforce that invariant explicitly (a no-op under the collapse, defensive). The
    # guard is set in create_regions only for unlock=vanilla + gems-not-shuffled;
    # OFF leaves the map untouched.
    if getattr(world, "_ctr_force_vanilla_turbotrack", False):
        _GUARDED_PADS = (
            "Turbo Track Warp Pad", "Slide Coliseum Warp Pad",
            "Red Cup Warp Pad", "Green Cup Warp Pad", "Blue Cup Warp Pad",
            "Yellow Cup Warp Pad", "Purple Cup Warp Pad",
        )
        for _pad in _GUARDED_PADS:
            out.pop(_pad, None)
    return out
