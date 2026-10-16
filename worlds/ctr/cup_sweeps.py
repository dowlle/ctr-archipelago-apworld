"""#246: one check for four first-place legs of an uninterrupted Gem Cup.

The world owns eligible Cups, exact ordered legs and the entrance/finish rules;
native owns the attempt record. Existing points-win Gem checks stay separate.
DATAPACKAGE STABILITY: uses the five already-minted 35028300..35028304 names.
No composed Cup or custom-track addressing code is changed by this module.
"""
from Options import OptionError
from .cup_checks import CUP_SWEEP_CLASS, GEM_CUPS, GEM_CUP_SWEEP_CODE_BASE
from .gem_cup_legs import cup_legs_to_wire, resolved_gem_cup_legs_table
from .Locations import create_location


def fail(message):
    raise OptionError('CTR cup sweep checks: '+message)


def restore_options(options, wire):
    flag=wire.get('ctr_options',{}).get('cup_sweep_checks',False)
    block=wire.get('cup_sweep_checks')
    if type(flag) is not bool or (flag and block is None) or (not flag and 'cup_sweep_checks' in wire):
        fail('option and block disagree')
    options.cup_sweep_checks.value=int(flag)
    options._cup_sweep_wire=block


def create_locations(world, regions):
    o=world.options
    o._cup_sweep_selected=()
    if not o.cup_sweep_checks.value:
        return
    legs=getattr(world,'gem_cup_legs',{})
    from .cortex_vortex_track import dropped_region
    dropped=dropped_region(o)
    selected=[]
    for cup in GEM_CUPS:
        if cup==dropped or cup not in regions or len(legs.get(cup,()))!=4:
            continue
        name=CUP_SWEEP_CLASS.location_name(cup)
        loc=create_location(world.player,name,regions[cup])
        loc.type='cup_sweep';loc.logic_text='True'
        regions[cup].locations.append(loc)
        world.multiworld.regions.location_cache[world.player][name]=loc
        selected.append(name)
    o._cup_sweep_selected=tuple(selected)
    if hasattr(o,'_cup_sweep_wire'):
        raw=o._cup_sweep_wire
        expected=wire_block(world)
        # Archipelago room persistence turns arrays into tuples. Compare their
        # JSON representation, preserving exact booleans/integer tokens.
        import json
        try:
            same=json.dumps(raw,sort_keys=True)==json.dumps(expected,sort_keys=True)
        except (ValueError,TypeError):
            same=False
        if not same:
            fail('saved Cup identities or ordered legs disagree with the selected content')


def wire_block(world):
    legs=cup_legs_to_wire(resolved_gem_cup_legs_table(world))
    names=set(getattr(world.options,'_cup_sweep_selected',()))
    return dict(version=1,cups={str(100+i):dict(location=GEM_CUP_SWEEP_CODE_BASE+i,
        legs=legs[str(100+i)]) for i,cup in enumerate(GEM_CUPS)
        if CUP_SWEEP_CLASS.location_name(cup) in names})


def install_rules(world,player):
    from .logic_terms import Cap, Families, Or, and_term
    from .capability_contract import difficulty_gated_tracks
    from .itemsanity import DIFFICULTY_WEAPON_FAMILY_MIN, USEFUL_WEAPON_FAMILIES
    from .progressive_capability import destination_pad_name
    from .usf_finish import cup_finish_t
    selected=set(getattr(world.options,'_cup_sweep_selected',()))
    for cup,legs in getattr(world,'gem_cup_legs',{}).items():
        name=CUP_SWEEP_CLASS.location_name(cup)
        if name not in selected:
            continue
        loc=world.multiworld.get_location(name,player)
        # The actual Cup pad supplies reachability and racer ownership. A
        # standalone track pad is never a prerequisite for racing its Cup leg.
        and_term(loc,cup_finish_t(legs,world,cup))
        if (world.options.progressive_boost.value and
                int(world.options.logic_difficulty.value)<2 and
                set(legs).intersection(difficulty_gated_tracks())):
            racer=(getattr(world,'ctr_racer_locks',{}) or {}).get(destination_pad_name(world,cup))
            term=Cap(world,1,racer)
            if world.options.itemsanity.value:
                term=Or(term,Families(USEFUL_WEAPON_FAMILIES,DIFFICULTY_WEAPON_FAMILY_MIN,player))
            and_term(loc,term)
