"""
Classes and functions related to creating a ROM patch
"""
from typing import Iterable
import json
import pkgutil

from BaseClasses import Location
from settings import get_settings
from worlds.Files import APProcedurePatch, APTokenMixin, APTokenTypes

# Import registers CtrPatchExtension with AutoPatchExtensionRegister at
# module import time, making "regenerate_ecc" resolvable during patch().
from . import Patches  # noqa: F401


FILENAME_CTR_TOKEN_BINARY: str = "ctr_token_data.bin"
MARKER_INTERNAL_DB_START: list = [0xDB, 0xDA, 0x00, 0x0D, 0xDB, 0xDA]
MARKER_INTERNAL_DB_END: list = [0xDB, 0xDA, 0xAA, 0x0D, 0xDB, 0xDD, 0xFF, 0xFF]


class CrashTeamRacingProcedurePatch(APProcedurePatch, APTokenMixin):
    game = "Crash Team Racing"
    hash = "ab95bfca8a4bb3d90daa6519acf6e944"
    patch_file_ending = ".apctr"
    result_file_ending = ".bin"

    procedure = [
        ("apply_bsdiff4", ["base_patch.bsdiff4"]),
        ("apply_tokens", [FILENAME_CTR_TOKEN_BINARY]),
        # Regenerate EDC+ECC for any sectors modified by the two steps above.
        # Required for BizHawk's PSX cores (Octoshock/Nymashock) to load the
        # patched ROM; DuckStation tolerates stale ECC but BizHawk freezes on
        # Adventure Mode load without this. See Patches.py.
        ("regenerate_ecc", []),
    ]

    @classmethod
    def get_source_data(cls) -> bytes:
        with open(get_settings()["crash_team_racing_settings"]["rom_file"], "rb") as infile:
            base_rom_bytes = bytes(infile.read())
        return base_rom_bytes


def write_tokens(
    patch: CrashTeamRacingProcedurePatch,
    item_placement: Iterable[Location],
) -> None:
    options_adress: int = 0xF1EC

    ctr_database: dict = get_ctr_database(item_placement)

    sorted_dbkeys: list = list(ctr_database.keys())
    sorted_dbkeys.sort()

    cur_pos: int = options_adress

    # Write "start of internal database" markers
    patch.write_token(
        token_type=APTokenTypes.WRITE,
        offset=cur_pos,
        data=bytes(MARKER_INTERNAL_DB_START),
    )
    cur_pos += 6

    # Write database
    for dbkey in sorted_dbkeys:
        dbvalue = ctr_database[dbkey]
        patch.write_token(
            token_type=APTokenTypes.WRITE,
            offset=cur_pos,
            data=bytes([
                (dbkey >> 16) & 0xFF,
                (dbkey >> 24) & 0xFF,
                dbkey & 0xFF,
                (dbkey >> 8) & 0xFF,
                dbvalue & 0xFF,
                (dbvalue >> 8) & 0xFF,
            ]),
        )

        cur_pos += 6

    # for location in world.multiworld.get_locations(world.player):
    #    print(location)
    #    print(location.item)

    # Write "end of internal database" markers
    patch.write_token(
        token_type=APTokenTypes.WRITE,
        offset=cur_pos,
        data=bytes(MARKER_INTERNAL_DB_END),
    )

    patch.write_file(FILENAME_CTR_TOKEN_BINARY, patch.get_token_binary())


def get_ctr_database(item_placement: Iterable[Location]) -> dict:
    ctr_db: dict = dict()

    # Load mapping data
    ctr_db_mapping = json.loads(
        pkgutil.get_data(__package__, "data/rom_db_mapping.json").decode("utf-8")
    )

    # STUB Write warp pad links
    for trackID in list(ctr_db_mapping["trackIDs"].values()):
        dbkey = (
            (ctr_db_mapping["db_prefixes"]["levelids"] << 16)
            | trackID << 16
        )
        dbvalue = trackID

        ctr_db[dbkey] = dbvalue

    # Write item placement
    for location in item_placement:
        track_name: str = location.name[:location.name.find(":")]
        race_name: str = location.name[location.name.find(":") + 2:]

        db_race_key = (
            "Trophy" if race_name == "Trophy Race"
            else "CTR Token" if race_name in ["CTR Token Challenge", "Crystal Bonus Round"]
            else "Sapphire Relic" if race_name == "Sapphire Time Trial"
            else "Gold Relic" if race_name == "Gold Time Trial"
            else "Platinum Relic" if race_name == "Platinum Time Trial"
            else "Key" if race_name == "Boss Race"
            else "INVALID"
        )
        if db_race_key == "INVALID":
            print(f"Invalid db_race_key for {location.name}")
        elif ctr_db_mapping["trackIDs"].get(track_name) is not None:
            # print(track_name)
            dbkey = (
                (ctr_db_mapping["db_prefixes"]["rewards"] << 16)
                | (ctr_db_mapping["trackIDs"][track_name] << 16)
                | ctr_db_mapping["items"][db_race_key]
            )

            if location.item is not None:
                item_name: str = location.item.name
                if item_name in ctr_db_mapping["items"]:
                    dbvalue = ctr_db_mapping["items"][item_name]

                    ctr_db[dbkey] = dbvalue
                    # print(f"{hex(dbkey)}/{hex(dbvalue)}")
                else:
                    print(f"nope: {location.item}")
        else:
            print(f"Invalid track_name: {track_name}")

    # STUB Write settings
    dbvalue = 0

    dbkey_relicdifficulty = (
        (ctr_db_mapping["db_prefixes"]["settings"] << 16)
    )
    ctr_db[dbkey_relicdifficulty] = dbvalue

    dbkey_relics_need_perfect = (
        (ctr_db_mapping["db_prefixes"]["settings"] << 16)
        | 1 << 16
    )
    ctr_db[dbkey_relics_need_perfect] = dbvalue

    dbkey_boss_garage_opening = (
        (ctr_db_mapping["db_prefixes"]["settings"] << 16)
        | 2 << 16
    )
    ctr_db[dbkey_boss_garage_opening] = dbvalue

    dbkey_qol_skip_maskhints = (
        (ctr_db_mapping["db_prefixes"]["settings"] << 16)
        | 3 << 16
    )
    ctr_db[dbkey_qol_skip_maskhints] = dbvalue

    dbkey_qol_skip_podium = (
        (ctr_db_mapping["db_prefixes"]["settings"] << 16)
        | 4 << 16
    )
    ctr_db[dbkey_qol_skip_podium] = dbvalue

    dbkey_qol_skip_maskcongrats = (
        (ctr_db_mapping["db_prefixes"]["settings"] << 16)
        | 5 << 16
    )
    ctr_db[dbkey_qol_skip_maskcongrats] = dbvalue

    dbkey_oxide_required_relics = (
        (ctr_db_mapping["db_prefixes"]["settings"] << 16)
        | 6 << 16
    )
    ctr_db[dbkey_oxide_required_relics] = dbvalue

    return ctr_db
