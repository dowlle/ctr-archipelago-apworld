import logging
import json
import os
from typing import Dict, List
import pkgutil

from BaseClasses import MultiWorld, Item, Tutorial, ItemClassification
from worlds.AutoWorld import World, CollectionState, WebWorld
from .Locations import get_location_names, get_total_locations
from .Items import load_item_table, item_prefix
from .Options import ctrAPOptions, Goal
from .Regions import create_regions
from .Rom import CrashTeamRacingProcedurePatch, write_tokens
from .Rules import set_rules
from .Types import ctrAPItem


class ctrAPWeb(WebWorld):
    theme = "Party"

    tutorials = [
        Tutorial(
            "Multiworld Setup Guide",
            "A guide to setting up Crash Team Racing for Archipelago, including "
            "single-player, multiworld, and required tools.",
            "English",
            "setup_en.md",
            "setup/en",
            ["Taor", "Icebound777"]
        )
    ]


class ctrAPWorld(World):
    """
    Crash Team Racing (CTR) is a kart racing game developed by Naughty Dog and published by Sony
    Computer Entertainment for the PlayStation in 1999.
    It features characters from the Crash Bandicoot series and combines fast-paced racing with
    power-ups and weapons.
    """

    game = "Crash Team Racing"
    web = ctrAPWeb()
    topology_present = True
    options_dataclass = ctrAPOptions
    options: ctrAPOptions

    # Item + Location mapping
    item_name_to_id = {
        item["name"]: (item_prefix + index)
        for index, item in enumerate(load_item_table())
    }
    location_name_to_id = get_location_names()

    def __init__(self, multiworld: "MultiWorld", player: int):
        super().__init__(multiworld, player)
        self.start_region = None

    def create_regions(self):
        create_regions(self)

    def set_rules(self):
        set_rules(self)

    # --- Item creation ---

    def create_item(self, name: str) -> "ctrAPItem":
        item_id: int = self.item_name_to_id[name]
        idx = item_id - item_prefix
        return ctrAPItem(
            name=name,
            classification=load_item_table()[idx]["classification"],
            code=item_id,
            player=self.player,
        )

    def create_event(self, event: str):
        return ctrAPItem(
            name=event,
            classification=ItemClassification.progression_skip_balancing,
            code=None,
            player=self.player,
        )

    def place_items_from_dict(self, option_dict: Dict[str, str]):
        for loc, item in option_dict.items():
            self.get_location(
                location_name=loc
            ).place_locked_item(
                item=self.create_item(item)
            )

    def create_filler(self, count: int) -> List[Item]:
        junk_pool: List[Item] = []
        for _ in range(count):
            junk_pool.append(self.create_item("Wumpa Fruit"))
        return junk_pool

    def create_items(self):
        player = self.player
        mw = self.multiworld
        pool = []

        if self.options.goal.value <= 2:
            victory = ctrAPItem(
                name="Victory",
                classification=ItemClassification.progression_skip_balancing,
                code=None,
                player=player,
            )

            match self.options.goal.value:
                case 0:
                    mw.get_location(
                        location_name="N. Oxide Garage: N. Oxide's Challenge",
                        player=player,
                    ).place_locked_item(victory)
                    mw.completion_condition[player] = lambda state: state.has(
                        item="Victory",
                        player=player,
                    )
                case 1:
                    mw.get_location(
                        location_name="N. Oxide Garage: N. Oxide's Final Challenge",
                        player=player,
                    ).place_locked_item(victory)
                    mw.completion_condition[player] = lambda state: state.has(
                        item="Victory",
                        player=player,
                    )
                case 2:
                    mw.get_location(
                        location_name="N. Oxide Garage: N. Oxide's Final Challenge",
                        player=player,
                    ).place_locked_item(victory)
                    mw.completion_condition[player] = (
                        lambda state:
                            state.has("Victory", player)
                            and state.has("Gold Relic", player, 18)
                            and all(state.has(g, player, 1)
                                    for g in ["Red Gem", "Green Gem", "Blue Gem", "Yellow Gem", "Purple Gem"]
                                )
                    )

        elif self.options.goal.value >= 3:
            match self.options.goal.value:
                case 3:
                    mw.completion_condition[player] = lambda state: state.has(
                        item="Trophy",
                        player=player,
                        count=16,
                    )
                case 4:
                    self.gemgoal(player)

        # --- Relic-tier progression sliders (pinned-vanilla lock per the slider roll) ---
        # For each tier, roll each of its 18 time-trial locations: with `chance`%
        # it stays progression-eligible, else pin that tier's vanilla relic there
        # (place_locked_item -> out of the multiworld pool). Track n_locked per tier
        # so the general pool below creates (18 - n_locked) of that relic, keeping
        # item count == location count (same invariant the gemgoal pass relies on).
        _relic_tiers = [
            ("Sapphire", "Sapphire Relic", self.options.sapphire_relic_progression.value),
            ("Gold", "Gold Relic", self.options.gold_relic_progression.value),
            ("Platinum", "Platinum Relic", self.options.platinum_relic_progression.value),
        ]
        # Precedence: only Platinum relics are pool-optional via ShuffleRewards.
        # If the user explicitly set "Include Platinum Relics" off, the relic is not
        # in the pool, so force platinum chance to 0 (it MUST be pinned). Sapphire/Gold
        # are always shuffled. Warn on the off + >0 corner.
        _shuf = dict(self.options.shuffle_rewards.value or {})
        if "Include Platinum Relics" in _shuf and not _shuf["Include Platinum Relics"]:
            if self.options.platinum_relic_progression.value > 0:
                logging.warning(
                    "[CTR] %s: 'Include Platinum Relics' is off; forcing "
                    "platinum_relic_progression to 0 (relic must be pinned).",
                    self.player_name,
                )
            _relic_tiers[2] = ("Platinum", "Platinum Relic", 0)

        # --- Two-stage content pinning (Regions.stage2_pin; set when two-stage active) ---
        # Lock each trophy pad's CTR Token Challenge + 3 relic Time Trials to their
        # own vanilla reward (Icebound fixed placement) so the stage-2 gates are
        # solvable under AP fill. _pinned tracks counts pulled out of the pool. The
        # relic-slider pass below SKIPS any location already pinned here (the 16
        # trophy pads' relics), so it only rolls the 2 trial pads while two-stage is
        # active; with two-stage inactive stage2_pin is empty and the sliders roll
        # all 18 per tier exactly as before.
        _stage2_pin = getattr(self, "stage2_pin", {})
        _pinned = {}  # item name -> count pinned out of the pool
        for _loc_name, _item in sorted(_stage2_pin.items()):
            if _loc_name in self.location_name_to_id:
                mw.get_location(_loc_name, player).place_locked_item(
                    self.create_item(_item)
                )
                _pinned[_item] = _pinned.get(_item, 0) + 1

        _relic_locked = {}  # relic item name -> count pinned out of the pool
        for _tier_label, _relic_item, _chance in _relic_tiers:
            _suffix = f": {_tier_label} Time Trial"
            _locs = sorted(n for n in self.location_name_to_id
                           if n.endswith(_suffix) and n not in _stage2_pin)
            _n = 0
            for _loc_name in _locs:
                if self.random.randint(0, 99) >= _chance:   # (100 - chance)% -> pin vanilla
                    mw.get_location(_loc_name, player).place_locked_item(
                        self.create_item(_relic_item)
                    )
                    _n += 1
            _relic_locked[_relic_item] = _relic_locked.get(_relic_item, 0) + _n

        # Merge the two-stage pins into the locked-count map for pool balancing.
        for _item, _c in _pinned.items():
            _relic_locked[_item] = _relic_locked.get(_item, 0) + _c

        # --- Create general item pool ---
        # For the all-gem-cups goal, gemgoal() LOCKS the 5 gems at the gem-cup
        # locations, so adding the same 5 gems from the item table again makes them
        # redundant progression items: the pool then exceeds the available
        # locations (gemgoal also consumes 5 cup locations) -> FillError ("N more
        # progression items than locations") and an item/location count mismatch.
        # Exclude the gems from the general pool for that goal (they are the goal
        # items, placed at the cups). Other goals keep gems in the pool (e.g.
        # everythingplusone needs them findable; Turbo Track logic needs them).
        _GEM_GOAL = self.options.goal.value == Goal.option_allgemcups
        _GEMS = {"Red Gem", "Green Gem", "Blue Gem", "Yellow Gem", "Purple Gem"}
        for item in load_item_table():
            if _GEM_GOAL and item["name"] in _GEMS:
                continue
            count = item["count"]
            if item["name"] in _relic_locked:                         # relics + two-stage pins
                count = max(0, count - _relic_locked[item["name"]])
            if count > 0:
                for _ in range(count):
                    pool.append(self.create_item(item["name"]))

        mw.itempool += pool
        # Size filler off the UNFILLED locations, i.e. total minus the locations
        # already locked above (the victory item, and for the gem-cup goal the 5
        # locked gems). Using the static get_total_locations over-counted by the
        # number of locked locations -> 1 (or 5) excess filler items -> the
        # item/location count mismatch the fuzzer flags. Clamp at 0 for safety.
        unfilled = len(mw.get_unfilled_locations(self.player))
        mw.itempool += self.create_filler(max(0, unfilled - len(mw.itempool)))

    def gemgoal(self, player):
        """Locks gem rewards in the appropriate Gem Cup locations."""
        # Read via pkgutil so it works when the world is loaded from a zipped
        # .apworld (open()/os.path on __file__ raises NotADirectoryError inside a
        # zip -- the gem-cup goal crashed on every distributed seed). pkgutil is
        # the mandatory pattern for all packaged data reads in this world.
        _mapping = json.loads(
            pkgutil.get_data(__package__, "data/vanilla_mapping.json").decode("utf-8")
        )
        mw = self.multiworld
        for loc_name, gem_name in _mapping["ShuffleOptions"]["Gems"].items():
            loc = mw.get_location(loc_name, player)
            loc.place_locked_item(self.create_item(gem_name))

        mw.completion_condition[player] = lambda state: all(
            state.has(g, player, 1)
            for g in ["Red Gem", "Green Gem", "Blue Gem", "Yellow Gem", "Purple Gem"]
        )

    # --- Native-randomization slot_data (Phase-2 MVP shared contract) ---

    # Native warp_pad_map / warp_pad_unlock arrays are indexed by pad LevelID
    # 0..27 (race/crystal/trial tracks). Gem cups (LevelID 100+) are handled
    # native-side via their own fixed rule, so they are NOT part of these arrays.
    WARP_PAD_ID_RANGE = 28

    def _resolve_warp_pad_map(self) -> Dict[str, int]:
        """{"<physicalPadLevelID>": <targetTrackID>} — ALWAYS present.

        Identity over the 28 in-range pad LevelIDs, then overlay any shuffle
        remap (STRETCH; empty in MVP -> stays identity).
        """
        m = {str(i): i for i in range(self.WARP_PAD_ID_RANGE)}
        pad_ids = getattr(self, "warp_pad_ids", {})
        for pad_name, target_track_id in getattr(self, "warp_pad_map", {}).items():
            meta = pad_ids.get(pad_name)
            if meta is None:
                continue
            lid = meta["level_id"]
            if 0 <= lid < self.WARP_PAD_ID_RANGE:
                m[str(lid)] = int(target_track_id)
        return m

    def _resolve_warp_pad_unlock(self) -> Dict[str, Dict[str, Dict[str, int]]]:
        """{"<padLevelID>": {"stage1": {type,count,colour},
                             "stage2": {type,count,colour}}} — ALWAYS present.

        Two-stage contract (Option A, schema_version 2). Stage 1 opens the pad's
        Trophy Race; stage 2 (the 16 trophy pads only) opens that pad's CTR Token
        Challenge + 3 relic Time Trials, ANDed on top of stage 1. Both are keyed by
        PHYSICAL pad LevelID. Every in-range pad defaults to stage1/stage2 type 0
        ({0,0,-1}) so a vanilla-mode / fixed / no-stage-2 pad falls back to native's
        own rule (type 0 stage 2 = native opens the token/relic menu immediately).
        """
        pad_ids = getattr(self, "warp_pad_ids", {})
        unlock = getattr(self, "warp_pad_unlock", {})
        unlock_s2 = getattr(self, "warp_pad_unlock_stage2", {})

        def _req(d):
            return {"type": int(d["type"]), "count": int(d["count"]),
                    "colour": int(d["colour"])}

        _ZERO = {"type": 0, "count": 0, "colour": -1}

        # Default all in-range pad LevelIDs to type 0 for both stages.
        out: Dict[str, Dict[str, Dict[str, int]]] = {}
        for meta in pad_ids.values():
            lid = meta["level_id"]
            if 0 <= lid < self.WARP_PAD_ID_RANGE:
                out[str(lid)] = {"stage1": dict(_ZERO), "stage2": dict(_ZERO)}

        # Overlay the per-seed randomized requirements (stage 1 + stage 2).
        for pad_name, req in unlock.items():
            meta = pad_ids.get(pad_name)
            if meta is None:
                continue
            lid = meta["level_id"]
            if 0 <= lid < self.WARP_PAD_ID_RANGE:
                out[str(lid)]["stage1"] = _req(req)
        for pad_name, req in unlock_s2.items():
            meta = pad_ids.get(pad_name)
            if meta is None:
                continue
            lid = meta["level_id"]
            if 0 <= lid < self.WARP_PAD_ID_RANGE:
                out[str(lid)]["stage2"] = _req(req)
        return out

    def fill_slot_data(self) -> Dict[str, object]:
        o = self.options
        slot_data: Dict[str, object] = {
            "Seed": self.multiworld.seed_name,
            "Slot": self.multiworld.player_name[self.player],
            "TotalLocations": get_total_locations(self),
            "ctr_options": {
                "schema_version": 2,
                "goal": o.goal.value,
                "relic_min_time": o.rr_required_minimum_time.value,
                "relics_require_perfect": bool(o.rr_require_perfects.value),
                "oxide_final_unlock": o.oxide_final_challenge_unlock.value,
                "shuffle_warp_pads": bool(o.shuffle_warp_pads.value),
                "warppad_unlock_mode": o.warppad_unlock_requirements.value,
                "bossgarage_mode": o.bossgarage_unlock_requirements.value,
            },
            "warp_pad_map": self._resolve_warp_pad_map(),
            "warp_pad_unlock": self._resolve_warp_pad_unlock(),
            "boss_garage_req": getattr(self, "boss_garage_req", {}),
        }
        return slot_data

    def collect(self, state: "CollectionState", item: "Item") -> bool:
        return super().collect(state, item)

    def remove(self, state: "CollectionState", item: "Item") -> bool:
        return super().remove(state, item)

    # --- Output generation ---

    def generate_output(self, output_directory: str) -> None:
        patch: CrashTeamRacingProcedurePatch = CrashTeamRacingProcedurePatch(
            player=self.player,
            player_name=self.player_name
        )
        pkg_ressource: bytes | None = pkgutil.get_data(
            package=__name__,
            resource="data/base_patch.bsdiff4",
        )
        if pkg_ressource is not None:
            patch.write_file(
                file_name="base_patch.bsdiff4",
                file=pkg_ressource,
            )
        else:
            None #todo we should really throw some kind of exception here

        write_tokens(
            patch=patch,
            item_placement=self.multiworld.get_locations(self.player),
        )

        # Write output
        out_file_name: str = self.multiworld.get_out_file_name_base(
            player=self.player,
        )
        patch.write(
            os.path.join(
                output_directory,
                f"{out_file_name}{patch.patch_file_ending}"
            )
        )


# Register the BizHawk client so `BizHawkClient` launcher can claim CTR ROMs.
# ADDED FOR CLIENT TESTING — not in upstream icebound777/ctr-apworld yet.
from . import client  # noqa: E402, F401

