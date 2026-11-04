"""Crystal Challenge content and the authored arcade identities (#259).

The apworld owns selection, checks and physical entry gates; native owns the
twenty authored crystal anchors, real collision and the completion signal.
Arcade completion grants no Purple Token. Timers are provisional test limits.

DATAPACKAGE STABILITY. The three arcade completion names register at 35028500
through 35028502; sixty position-owned pickups register at 35028520 through
35028579, in Parking Lot, The North Bowl, Lab Basement order. Registration is
unconditional; generation creates only selected content. Existing ids never move.
"""
import json
import pkgutil
from .location_class import LocationClass
from .crystal_checks import CRYSTAL_ARENAS, ARENA_LEVELS, CRYSTAL_CLASS

ARCADE_DATA = json.loads(pkgutil.get_data(__package__, 'data/arcade_arenas_v1.json'))
ARCADE = {row['level_id']: row for row in ARCADE_DATA['arenas']}
ARENAS = dict(zip(ARENA_LEVELS, CRYSTAL_ARENAS)) | {lid: row['name'] for lid,row in ARCADE.items()}
TIMERS = dict(zip(ARENA_LEVELS, (79680,81600,76800,115200))) | {lid: row['time_limit_ticks'] for lid,row in ARCADE.items()}

def completion_code(level):
    return ARCADE[level]['completion_location'] if level in ARCADE else 35013000+ARENA_LEVELS.index(level)

def pickup_code(level, number):
    if type(number) is not int or not 1 <= number <= 20:
        raise ValueError('crystal number must be 1..20')
    return (ARCADE[level]['crystal_locations'][number-1] if level in ARCADE else
            CRYSTAL_CLASS.code_for(ARENAS[level],number))

def checks(entry, pad_id, crystalsanity):
    level=entry['arena_id']
    owner=f'arena:{level}'
    route=dict(entry_id=entry['id'],mode='crystal',leg_id=None,encounter_id=None,own_pad_id=pad_id,award='complete')
    result=[dict(location=completion_code(level),owner=owner,kind='crystal',
                 display_name=ARENAS[level]+': Crystal Challenge',routes=[route])]
    if crystalsanity:
        for n in range(1,21):
            result.append(dict(location=pickup_code(level,n),owner=owner,kind='crystal_pickup',
                display_name=f'{ARENAS[level]}: Crystal {n:02d}',routes=[dict(route,award=f'crystal:{n:02d}')]))
    return result

class ArcadeArenaLocationClass(LocationClass):
    key='arcade_arena'
    display_name='Arcade Arena Checks'
    code_blocks=(35028500,35028520)
    def all_locations(self):
        out=[]
        for lid,row in ARCADE.items():
            out.append((row['name']+': Crystal Challenge',completion_code(lid),row['name']))
            out.extend((f"{row['name']}: Crystal {n:02d}",pickup_code(lid,n),row['name']) for n in range(1,21))
        return out
    def created_location_names(self,options):
        # The content plan owns the selected subset and creates its regions.
        return []

ARCADE_ARENA_CLASS=ArcadeArenaLocationClass()
