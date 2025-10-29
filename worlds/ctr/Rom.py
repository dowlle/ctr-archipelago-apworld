"""
Classes and functions related to creating a ROM patch
"""

from settings import get_settings
from worlds.Files import APProcedurePatch, APTokenMixin, APTokenTypes


FILENAME_CTR_TOKEN_BINARY: str = "ctr_token_data.bin"
MARKER_INTERNAL_DB_START: list = [0xDA, 0xDB, 0x0D, 0x00, 0xDA, 0xDB]
MARKER_INTERNAL_DB_END: list = [0xDA, 0xDB, 0x0D, 0xAA, 0xDA, 0xDB, 0xFF, 0xFF]


class CrashTeamRacingProcedurePatch(APProcedurePatch, APTokenMixin):
    game = "Crash Team Racing"
    hash = "ab95bfca8a4bb3d90daa6519acf6e944"
    patch_file_ending = ".apctr"
    result_file_ending = ".bin"

    procedure = [
        ("apply_bsdiff4", ["base_patch.bsdiff4"]),
        ("apply_tokens", [FILENAME_CTR_TOKEN_BINARY]),
    ]

    @classmethod
    def get_source_data(cls) -> bytes:
        with open(get_settings()["crash_team_racing_settings"]["rom_file"], "rb") as infile:
            base_rom_bytes = bytes(infile.read())
        return base_rom_bytes


def write_tokens(world, patch: CrashTeamRacingProcedurePatch) -> None:
    options_adress: int = 0xF1F4

    #sorted_dbkeys: list = list(randomized_database.keys())
    #sorted_dbkeys.sort()

    cur_pos: int = options_adress

    # Write "start of internal database" markers
    patch.write_token(
        APTokenTypes.WRITE,
        cur_pos,
        bytes(MARKER_INTERNAL_DB_START),
    )
    cur_pos += 6

    # Write database
    #for dbkey in sorted_dbkeys:
    #    dbvalue = randomized_database[dbkey]
    #    patch.write_token(
    #        APTokenTypes.WRITE,
    #        cur_pos,
    #        bytes([
    #            (dbkey >> 24) & 0xFF,
    #            (dbkey >> 16) & 0xFF,
    #            (dbkey >> 8) & 0xFF,
    #            dbkey & 0xFF,
    #            (dbvalue >> 8) & 0xFF,
    #            dbvalue & 0xFF,
    #        ]),
    #    )
#
    #    cur_pos += 6

    # Write "end of internal database" markers
    patch.write_token(
        APTokenTypes.WRITE,
        cur_pos,
        bytes(MARKER_INTERNAL_DB_END),
    )

    patch.write_file(FILENAME_CTR_TOKEN_BINARY, patch.get_token_binary())
