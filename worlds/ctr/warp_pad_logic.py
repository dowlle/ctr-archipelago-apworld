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
# Key 1 (cups are native-fixed and excluded). The sphere-search reasons over these
# so it never assigns a requirement behind a Key wall it cannot yet pass.
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
    # NOTE: Slide Coliseum / Turbo Track (trial pads) and the gem cups are
    # native-fixed and NOT randomized -> deliberately excluded from this map so
    # the sphere-search never assigns them a requirement.
}

# Vanilla per-pad trophy floor (numTrophiesToOpen), keyed by the PHYSICAL pad
# (= track name). Verified from the CTR-native decomp (zGlobal_DATA.c MetaDataLEV
# .numTrophiesToOpen) AND from data/world.json's "<track>: Trophy Race" requires.
#
# A trophy-race pad only opens once the player's RECEIVED Trophy count reaches
# this floor, and native keys it by the PHYSICAL pad (ap_hooks.c
# ctr_cfg_warp_unlocked + AH_WarpPad.c LInB use the physical levelID). world.json
# instead keyed it on the trophy-race LOCATION by track; under destination shuffle
# that mis-keys the floor to the DESTINATION track (a low-floor physical pad
# loading a high-floor track inherited the wrong floor) -> the shuffle progression
# stall. The fix keys the floor by PHYSICAL pad in three consistent places: this
# sphere-search reachability model, Rules (the free pad's exit rule), and removing
# the redundant track-keyed location floor in create_regions.
#
# Native applies the floor ONLY to free (type:0) pads; a pad with a per-seed
# requirement uses ONLY that requirement (floor XOR per-seed). So the floor is
# enforced here exclusively where a pad stays free. Only the 16 trophy-race pads
# have a floor; crystal/arena pads and trials/cups gate differently (absent -> 0).
TRACK_TROPHY_GATE = {
    "Crash Cove": 0, "Roo's Tubes": 0, "Mystery Caves": 1, "Sewer Speedway": 3,
    "Tiger Temple": 4, "Coco Park": 4, "Papu's Pyramid": 6, "Dingo Canyon": 7,
    "Blizzard Bluff": 8, "Dragon Mines": 9, "Polar Pass": 10, "Tiny Arena": 11,
    "Cortex Castle": 12, "N. Gin Labs": 12, "Hot Air Skyway": 14,
    "Oxide Station": 15,
}

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

# The 5 N. Sanity Beach candidates for the free subset, weighted sizes.
FREE_CANDIDATES = ["Crash Cove", "Roo's Tubes", "Mystery Caves",
                   "Sewer Speedway", "Skull Rock"]
FREE_SIZE_WEIGHTS = [(1, 10), (2, 30), (3, 30), (4, 15), (5, 15)]
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


def build_graph(world, reward_track_for):
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
            reward = _vanilla_reward(rname, rtype, dest_track, sfx)
            is_tt = name.endswith("Time Trial") or name.endswith("CTR Token Challenge")
            trophy_loc = None
            if is_tt:
                trophy_loc = name.split(":", 1)[0].strip() + ": Trophy Race"
            locations[name] = {
                "region": rname, "reward": reward, "gate": gate,
                "is_tt_or_token": is_tt, "trophy_loc": trophy_loc,
            }
    return exits, locations, region_type


def _vanilla_reward(region_name, region_type, dest_track, suffix):
    """Vanilla reward a location yields, for inventory growth in the sphere search.
    Boss races (except Oxide) yield a Key; gem cups yield nothing here (cups are
    native-fixed and not in the pool); race/crystal locations yield their reward."""
    if region_type == "boss":
        return None if "Oxide" in region_name else "Key"
    if region_type == "cup":
        return None  # gem cups are native-fixed; not part of the sphere pool
    track = region_name
    return _reward_for(track, dest_track, suffix)


# ---------------------------------------------------------------------------
# Requirement weighting + Any* collapse (ports lines 250-366)
# ---------------------------------------------------------------------------

REQ_WEIGHTS = {
    "Trophy": 100, "Key": 25,
    "Red CTR Token": 15, "Green CTR Token": 15, "Blue CTR Token": 15,
    "Yellow CTR Token": 15, "Purple CTR Token": 10,
    "Sapphire Relic": 20, "Gold Relic": 20, "Platinum Relic": 20,
    "Red Gem": 2, "Green Gem": 2, "Blue Gem": 2, "Yellow Gem": 2, "Purple Gem": 2,
}
TOKEN_ITEMS = ("Red CTR Token", "Green CTR Token", "Blue CTR Token",
               "Yellow CTR Token", "Purple CTR Token")
RELIC_ITEMS = ("Sapphire Relic", "Gold Relic", "Platinum Relic")
GEM_ITEMS = ("Red Gem", "Green Gem", "Blue Gem", "Yellow Gem", "Purple Gem")


def _weighted_choice(rnd, pairs):
    """pairs = [(value, weight)]; returns one value via rnd.choices."""
    values = [v for v, _ in pairs]
    weights = [w for _, w in pairs]
    return rnd.choices(values, weights=weights, k=1)[0]


def _choose_requirement(rnd, inv):
    """Port of lines 268-366: pick an owned item type, weight it, maybe collapse
    to an Any* aggregate. Returns (req_item, count). Any* is resolved to a
    concrete owned colour by the caller (run_sphere_search) so native needs no
    'any' aggregate support and solvability is preserved."""
    cands = [(it, inv.items[it]) for it in REQ_WEIGHTS if inv.items[it] > 0]
    cands.sort()  # Rust sorts possible_reqs before weighting
    chosen = _weighted_choice(rnd, [(c, REQ_WEIGHTS[c[0]]) for c in cands])
    req_item, req_cnt = chosen[0], chosen[1]

    if req_item in TOKEN_ITEMS:
        if rnd.randrange(100) < 33:
            total = inv.count("AnyCtrToken")
            req_item, req_cnt = "AnyCtrToken", max(1, math.ceil(total * 0.6))
    elif req_item in RELIC_ITEMS:
        if rnd.randrange(100) < 20:
            total = inv.count("AnyRelic")
            req_item, req_cnt = "AnyRelic", max(1, math.ceil(total * 0.3))
    elif req_item in GEM_ITEMS:
        if rnd.randrange(100) < 80:
            total = inv.count("AnyGem")
            # Rust subtracts 1 inside the accumulation loop (count - 1, floored at 1)
            req_item, req_cnt = "AnyGem", max(1, total - 1)
    return (req_item, req_cnt)


def _resolve_any(inv, req):
    """Lower an Any* requirement to the single owned colour with the most copies,
    so the AP rule + slot_data emit a concrete {type,colour,count} that Inv has
    proven is owned. Keeps solvability and avoids native 'any' support."""
    item, cnt = req
    if item == "AnyCtrToken":
        pool = Inv._TOKENS
    elif item == "AnyRelic":
        pool = Inv._RELICS
    elif item == "AnyGem":
        pool = Inv._GEMS
    else:
        return req
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


def _reachable_pads_and_collect(inv, exits, locations, pad_reqs, collected, start):
    """Sweep the AP graph with the current inventory + the per-pad requirements
    decided so far, collecting every reachable location's vanilla reward into the
    inventory (to a fixed point). Returns the set of OPEN, still-unassigned pads
    whose pad-exit is now traversable (candidates for the next requirement).

    A warp-pad exit (named '<track> Warp Pad') is traversable iff its static gate
    passes AND the pad is either free/assigned (pad_reqs has it -> its requirement,
    None=free, is enforced) OR it is the pad we are about to assign (handled by the
    caller: unassigned pads are treated as OPEN with NO extra requirement here, so
    we discover which pads are *reachable to assign*)."""
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
                    if req is None:
                        # Free pad (slot_data type:0): native gates entry on the
                        # PHYSICAL pad's vanilla trophy floor (numTrophiesToOpen),
                        # not the destination track's. Model it so the sphere-search
                        # agrees with native + AP fill (the track-keyed location
                        # floor is removed in create_regions; Rules re-adds this same
                        # floor to the free pad's exit).
                        if inv.count("Trophy") < TRACK_TROPHY_GATE.get(track, 0):
                            continue
                    elif not passes([req]):
                        continue  # assigned requirement not yet met
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
            if meta["reward"]:
                inv.add(meta["reward"])
            collected.add(name)
            changed = True
    return open_unassigned


def run_sphere_search(world, mode, reward_track_for=None):
    """Returns {track_name: (req_item, count) or None} for all shuffleable pads.
    None = free pad. mode 2 = random_without_4_keys. Deterministic on world.random.

    AP-correct, graph-driven port: reachability is computed over the LIVE AP region
    graph (the exact logic AP fill enforces), so every requirement assigned to a
    pad is provably satisfiable by items collectable strictly BEFORE that pad opens
    -> the produced DAG is solvable by construction under AP's real rules.

    reward_track_for(track) -> the track this physical pad actually loads (handles
    destination shuffle); defaults to identity.
    """
    rnd = world.random
    if reward_track_for is None:
        reward_track_for = lambda t: t

    exits, locations, _ = build_graph(world, reward_track_for)
    start = world.start_region.name if world.start_region else "Menu"

    # 1) free subset of the 5 N. Sanity Beach candidates
    size = _weighted_choice(rnd, FREE_SIZE_WEIGHTS)
    free = rnd.sample(FREE_CANDIDATES, size)
    # SOLVABILITY GUARANTEE: the sphere must start. Crash Cove is the only pad
    # whose trophy race is winnable from an empty inventory (Trophy 0), so ensure
    # a Trophy-0 bootstrap is free if the random subset didn't provide one.
    if "Crash Cove" not in free:
        free = free + ["Crash Cove"]

    pad_reqs = {t: None for t in free}  # free pads -> None

    inv = Inv()
    collected = set()
    _reachable_pads_and_collect(inv, exits, locations, pad_reqs, collected, start)

    remaining_pads = sorted(t for t in HUB_STATIC if t not in pad_reqs)

    # 2) sphere loop: until every pad has a requirement
    guard = 0
    max_iter = len(HUB_STATIC) * 8 + 64
    while remaining_pads:
        guard += 1
        if guard > max_iter:
            raise RuntimeError("CTR warp-pad sphere-search failed to converge")

        open_unassigned = _reachable_pads_and_collect(
            inv, exits, locations, pad_reqs, collected, start)
        reachable = sorted(t for t in remaining_pads if t in open_unassigned)
        if not reachable:
            # No statically-reachable unassigned pad. Assign the cheapest-Key pad
            # a FREE-ish minimal requirement so the graph can open further (this is
            # the rare residual case; counts stay satisfiable because we only ever
            # pick from currently-owned item types below).
            reachable = sorted(remaining_pads,
                               key=lambda t: (_max_key(HUB_STATIC[t]), t))[:1]

        track = rnd.choice(reachable)

        # choose a requirement TYPE from items currently in inventory. If the
        # inventory is somehow empty (degenerate), leave the pad free.
        if any(inv.items[it] > 0 for it in REQ_WEIGHTS):
            req = _choose_requirement(rnd, inv)
            req = _resolve_any(inv, req)  # lower Any* to a concrete owned colour
            # clamp count to what is currently owned (never exceed reachable supply)
            item, cnt = req
            owned = inv.count(item)
            if owned > 0:
                req = (item, min(cnt, owned))
            else:
                req = None
        else:
            req = None
        pad_reqs[track] = req
        remaining_pads.remove(track)

        # collect newly-reachable rewards now that this pad is open
        _reachable_pads_and_collect(inv, exits, locations, pad_reqs, collected, start)

    # 3) post-pass (ports lines 465-510), over a sorted copy. Only LOWERS counts,
    # so it cannot break the solvable DAG built above.
    _post_process(rnd, pad_reqs, mode)
    return pad_reqs


def _post_process(rnd, pad_reqs, mode):
    """66% lower count *0.6 ceil (when count != 0); else if mode==2 and req is
    ('Key',4) -> ('Key',3). Iterate a SORTED copy for determinism."""
    for track in sorted(pad_reqs):
        req = pad_reqs[track]
        if req is None:
            continue
        item, cnt = req
        if rnd.randrange(100) < 66:
            if cnt != 0:
                pad_reqs[track] = (item, max(1, math.ceil(cnt * 0.6)))
        elif mode == 2 and item == "Key" and cnt == 4:
            pad_reqs[track] = ("Key", 3)


# ---------------------------------------------------------------------------
# Map sphere output -> slot_data {type,count,colour} contract
# ---------------------------------------------------------------------------

_COLOURS = ["Red", "Green", "Blue", "Yellow", "Purple"]


def to_slot_req(req):
    """(item, count) | None -> {type,count,colour}.

    type: 0 none / 1 trophies / 2 keys / 3 tokens / 4 sapphire-relic / 5 gems.
    colour 0..4 = R,G,B,Y,P for token/gem; -1 otherwise. Any* are already
    resolved to a concrete colour upstream (_resolve_any), so no -1 token/gem
    aggregate is ever emitted here."""
    if req is None:
        return {"type": 0, "count": 0, "colour": -1}
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
# unique dispatch -> NOT shuffled (stay identity / native-fixed). Crystal/battle
# pads share a type -> shuffle among themselves. LevelIDs from warp_pad_ids.json.
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
