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

import math


# ---------------------------------------------------------------------------
# Static data -- the vanilla world (track-name strings instead of the Rust enum)
# ---------------------------------------------------------------------------

# Hub-door static gate per shuffleable track, mirroring the AP exit-graph Key
# gates (data/world.json). N. Sanity Beach pads ungated; Lost Ruins behind Key 1
# (Rampage Ruins behind Key 2); Glacier behind Key 2 (Rocky Road behind Key 3);
# Citadel behind Key 3 (Nitro Court behind Key 4); Gem Stone Valley trials behind
# Key 1; Gem Stone Valley gem cups behind Key 2 (the Cups Room hub gate, native
# arrKeysNeeded[GEM_STONE_VALLEY]=2 -- NOT 3). The
# sphere-search reasons over these so it never assigns a requirement behind a Key
# wall it cannot yet pass.
HUB_STATIC = {
    # N. Sanity Beach -- no hub gate
    "Crash Cove": [], "Roo's Tubes": [], "Mystery Caves": [],
    "Sewer Speedway": [], "Skull Rock": [],
    # Lost Ruins -- Key 1 (Rampage Ruins crystal behind Key 2)
    "Coco Park": [("Key", 1)], "Tiger Temple": [("Key", 1)],
    "Papu's Pyramid": [("Key", 1)], "Dingo Canyon": [("Key", 1)],
    "Rampage Ruins": [("Key", 2)],
    # Glacier Park -- Key 2 (Rocky Road crystal behind Key 3)
    "Blizzard Bluff": [("Key", 2)], "Dragon Mines": [("Key", 2)],
    "Polar Pass": [("Key", 2)], "Tiny Arena": [("Key", 2)],
    "Rocky Road": [("Key", 3)],
    # Citadel City -- Key 3 (Nitro Court crystal behind Key 4)
    "Hot Air Skyway": [("Key", 3)], "Cortex Castle": [("Key", 3)],
    "N. Gin Labs": [("Key", 3)], "Oxide Station": [("Key", 3)],
    "Nitro Court": [("Key", 4)],
    # Gem Stone Valley TRIAL pads -- behind Key 1 (N. Sanity Beach <-> Gem Stone
    # Valley). Slide Coliseum + Turbo Track have NO trophy race and NO CTR-token
    # challenge: only the 3 relic Time Trials (verified against data/world.json).
    # They are SINGLE-STAGE (no stage 2) but DO get a randomized stage-1 entry
    # requirement (Stef's OPEN model) -- excluded from TROPHY_TRACKS below so the
    # sphere-search assigns them only a tier-1 req. Their vanilla relic/gem JSON
    # gate is REPLACED by this randomized requirement in Rules.add_warp_pad_unlock_rules
    # (keeping only the Key-1 hub gate).
    "Slide Coliseum": [("Key", 1)], "Turbo Track": [("Key", 1)],
    # Gem Stone Valley GEM-CUP pads -- behind Key 3 (the Cups Room hub gate:
    # 'Gem Stone Valley <-> Cups Room' = has('Key', 3) in data/world.json). Each
    # cup yields a Gem on completion ('<Colour> Gem Cup: Gem'). Like the trials they
    # are SINGLE-STAGE (no stage 2) but DO get a randomized stage-1 entry requirement
    # (Stef's OPEN model) -- excluded from TROPHY_TRACKS AND from CUP_TRACKS below so
    # the sphere-search assigns them only a tier-1 req. Their vanilla per-cup
    # has('<Colour> CTR Token', 4) JSON gate is REPLACED by this randomized requirement
    # in Rules.add_warp_pad_unlock_rules, keeping ONLY the Key-3 Cups Room hub gate
    # (the randomized req is ANDed on TOP of that key gate, never replaces it). The
    # track key is '<Colour> Cup' so _pad_exit_name yields '<Colour> Cup Warp Pad'
    # (the AP exit name); the destination region is '<Colour> Gem Cup'. Gem cups are
    # NOT destination-shuffled (unique native dispatch -> absent from SHUFFLE_GROUPS),
    # only their UNLOCK REQUIREMENT is randomized. Gated in the emitter by the
    # include_gem_cups YAML option (mirrors include_battle_arenas for crystals).
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

    variety_opt = getattr(world.options, "requirement_variety", None)
    # Choice options expose .current_key ("icebound_beta5" etc.); fall back to legacy.
    preset = getattr(variety_opt, "current_key", "trophy_heavy_legacy")

    if preset == "icebound_beta5":
        REQ_WEIGHTS = dict(_REQ_WEIGHTS_ICEBOUND_BETA5)
        collapse_key = "icebound_beta5"
    elif preset == "custom":
        weights = dict(_REQ_WEIGHTS_TROPHY_HEAVY_LEGACY)  # fallback for omitted keys
        custom = getattr(getattr(world.options, "requirement_weights", None),
                         "value", None) or {}
        for k, v in custom.items():
            if k in weights:  # ignore stray keys; keep the key universe stable
                weights[k] = v
        REQ_WEIGHTS = weights
        collapse_key = "custom"
    else:  # trophy_heavy_legacy + any unknown/missing value
        REQ_WEIGHTS = dict(_REQ_WEIGHTS_TROPHY_HEAVY_LEGACY)
        collapse_key = "trophy_heavy_legacy"

    (_TOKEN_COLLAPSE_CHANCE, _TOKEN_COLLAPSE_SCALE, _TOKEN_COLLAPSE_CAP,
     _RELIC_COLLAPSE_CHANCE, _RELIC_COLLAPSE_SCALE, _RELIC_COLLAPSE_CAP,
     _GEM_COLLAPSE_CHANCE, _GEM_COLLAPSE_CAP) = _ANY_COLLAPSE_PARAMS[collapse_key]


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
    picked as a concrete requirement. This is Stef's "if a seed is tight, make do
    with the other item types" turned into a sphere-search rule -- the sliders stay
    authoritative and are never silently overridden."""
    pool_items = REQ_WEIGHTS if allowed is None else [
        it for it in REQ_WEIGHTS if it in allowed]
    cands = [(it, inv.items[it]) for it in pool_items if inv.items[it] > 0]
    if not cands:
        return None
    cands.sort()  # Rust sorts possible_reqs before weighting
    chosen = _weighted_choice(rnd, [(c, REQ_WEIGHTS[c[0]]) for c in cands])
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
    never resolves to a pinned-out relic tier)."""
    item, cnt = req
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
# (Trophy / Key / every CTR-token colour / every relic tier / every gem) -- Stef's
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
# remaining real gates. This is Stef's sanctioned "tier 2 MAY collapse if a seed
# needs it" turned into a small uniform relief valve; the golden path is unaffected
# (tier 1 is always satisfiable-by-construction). Tuned empirically against the
# two-stage-active FillError tail (see the impl A/B sweep).
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


def run_sphere_search(world, mode, reward_track_for=None, collapse_stage2=False,
                      include_gem_cups=False):
    """Returns {track_name: {1: stage1_req, 2: stage2_req}} for all shuffleable
    pads. Each req is (item, count) or None (free / no-gate). Stage 2 is non-None
    only for the 16 trophy pads (others get 2: None). mode 2 = random_without_4_keys.
    Deterministic on world.random.

    collapse_stage2 (= the autounlock_ctrchallenge_relicrace option): when True,
    every stage 2 is left OPEN (no requirement) -- Icebound's clear_stage2_unlocks,
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
    """
    rnd = world.random
    # Load the requirement-weight preset (icebound_beta5 default) into the module
    # globals BEFORE REQ_WEIGHTS / the `allowed` filter below are read. Re-run every
    # call so multi-seed processes never inherit a previous seed's preset.
    _load_requirement_preset(world)
    if reward_track_for is None:
        reward_track_for = lambda t: t

    # Slider-aware requirement filter (Stef's generation-control knob, honoured not
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
    # "makes do with the other item types" exactly as Stef specified; the sliders
    # are never silently overridden, only respected as the scarcity signal they are.
    # Default sliders (S100/G100/P0): sapphire+gold usable, platinum excluded.
    _slider = {
        "Sapphire Relic": getattr(world.options, "sapphire_relic_progression").value,
        "Gold Relic": getattr(world.options, "gold_relic_progression").value,
        "Platinum Relic": getattr(world.options, "platinum_relic_progression").value,
    }
    allowed = {it for it in REQ_WEIGHTS
               if it not in RELIC_ITEMS or _slider.get(it, 0) >= 100}

    exits, locations, _ = build_graph(world, reward_track_for, include_gem_cups)
    start = world.start_region.name if world.start_region else "Menu"

    # 1) free subset of the 5 N. Sanity Beach candidates -- the bootstrap pads
    # that are open at spawn (sphere 0). FULLY random: a random-sized (weighted
    # 1..5) random sample, no pinned pad. In randomized mode the vanilla trophy
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
    # deviation from Icebound's 1..5 weighting that strengthens Stef's golden-path
    # guarantee (collecting always unlocks something new). Sizes >= the floor keep
    # their original relative weights.
    size = max(_FREE_MIN, _weighted_choice(rnd, FREE_SIZE_WEIGHTS))
    free = rnd.sample(FREE_CANDIDATES, size)

    pad_reqs = {t: None for t in free}  # stage-1 reqs (physical-track keyed)
    # stage2_reqs: dest-track keyed; only the 16 trophy tracks. When collapsed
    # (autounlock), pre-set every trophy track to None (= open, no stage-2 gate)
    # so the loop never assigns one and collection never holds rewards back.
    stage2_reqs = {t: None for t in TROPHY_TRACKS} if collapse_stage2 else {}

    # dest-track -> physical-pad track, so a stage-2 fallback can collapse to the
    # SAME pad's stage-1 requirement. Under destination shuffle the locations of
    # dest D live in region D, but D's pad ENTRY requirement is the physical pad P
    # with reward_track_for(P) == D. Identity when shuffle is off.
    dest_to_phys = {}
    for _p in HUB_STATIC:
        dest_to_phys.setdefault(reward_track_for(_p), _p)

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
    guard = 0
    max_iter = len(HUB_STATIC) * 16 + 128
    s2_real_count = 0  # how many REAL (non-collapsed) stage-2 gates assigned so far
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
                else:
                    s2_real_count += 1
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
                reachable = sorted(remaining_pads,
                                   key=lambda t: (_max_key(HUB_STATIC[t]), t))[:1]
            track = rnd.choice(reachable)
            pad_reqs[track] = _assign_from_inv(rnd, inv, allowed)
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

    # 4) assemble {track: {1: stage1, 2: stage2}}. Stage 2 for a physical pad is
    # the req keyed by the track it LOADS (reward_track_for); non-trophy pads have
    # no stage 2.
    out = {}
    for t in HUB_STATIC:
        s2 = stage2_reqs.get(reward_track_for(t)) if t in TROPHY_TRACKS else None
        out[t] = {1: pad_reqs.get(t), 2: s2}
    return out


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


def to_slot_req(req):
    """(item, count) | None -> {type,count,colour}.

    type: 0 none / 1 trophies / 2 keys / 3 tokens / 4 sapphire-relic / 5 gems.
    colour 0..4 = R,G,B,Y,P for token/gem; -1 otherwise. Any* are already
    resolved to a concrete colour upstream (_resolve_any), so no -1 token/gem
    aggregate is ever emitted here.

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
    if item == "Trophy":
        return {"type": 1, "count": cnt, "colour": -1}
    if item == "Key":
        return {"type": 2, "count": cnt, "colour": -1}
    if item.endswith("CTR Token"):
        return {"type": 3, "count": cnt, "colour": _COLOURS.index(item.split()[0])}
    if item.endswith("Relic"):
        return {"type": 4, "count": cnt, "colour": -1}
    if item.endswith("Gem"):
        return {"type": 5, "count": cnt, "colour": _COLOURS.index(item.split()[0])}
    raise ValueError(f"unmappable warp-pad requirement item: {item!r}")


# ---------------------------------------------------------------------------
# Destination shuffle -- non-identity warp_pad_map
# ---------------------------------------------------------------------------

# Shuffle ONLY within the same native unlock-dispatch category, else the game
# split-keys it (AH_WarpPad ThTick dispatches by DESTINATION track while the
# unlock requirement keys off the PHYSICAL pad). The 16 main trophy-race pads
# all share one dispatch type -> safe to permute among themselves. The two trials
# (16 Slide Coliseum = relic, 17 Turbo Track = gem) and the 5 gem cups each have
# unique dispatch -> their DESTINATION is NOT shuffled (stay identity); only their
# UNLOCK REQUIREMENT is randomized (see HUB_STATIC / run_sphere_search). Crystal/
# battle pads share a type -> shuffle among themselves. LevelIDs from warp_pad_ids.json.
SHUFFLE_GROUPS = {
    # 16 trophy-race pads ONLY (trials 16/17 excluded -> stay fixed)
    "race": [3, 6, 9, 8, 14, 4, 5, 0, 2, 1, 12, 15, 7, 10, 11, 13],
    "crystal": [21, 19, 23, 18],
}


def build_warp_pad_map(world):
    """{pad_exit_name -> target_track_levelID}. Permutes destinations within each
    group; re-rolls if the whole permutation is identity. Respects
    include_battle_arenas (crystal group)."""
    rnd = world.random
    id_to_name = {meta["level_id"]: name
                  for name, meta in world.warp_pad_ids.items()}
    out = {}
    groups = ["race"]
    if bool(world.options.include_battle_arenas.value):
        groups.append("crystal")
    for g in groups:
        ids = list(SHUFFLE_GROUPS[g])
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
