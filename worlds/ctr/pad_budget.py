"""The 27 normal pads are one budget (A4-83, maintainer ruling 2026-11-14 about
15:16 CET: "Maybe we should interpret having more than 27 as a sort of weights
instead of having max 27? But we should make that very clear in the YAML").

WHAT TAKES A PAD. Every cup (`cup_count`), every Crystal Challenge
(`crystal_challenge_count`), every track that `required_entries` names, and
Cortex Vortex with `cortex_vortex_track: own_pad`. An arena that
`required_entries` names is one of the Crystal Challenges, not a pad of its
own. Tracks fill the pads that are left; they never push anything out.

FIT. When the cups, the Crystal Challenges and the required tracks add up to
27 or less, nothing here changes: no option is touched and no random number is
drawn, so the seed is exactly what it was before this module.

OVER THE BUDGET. The required tracks keep their pads first (they are promises).
The pads that are left are shared between the cups and the Crystal
Challenges in proportion to the requested counts, so the counts act as
weights:

    quota = pads left * request / sum of requests

Each count gets the whole part of its quota, and the pads still free go one
at a time to the largest fractional parts; on a tie cups come before Crystal
Challenges. A count never ends above its request and never below its floor:
the Crystal Challenge floor is the arenas `required_entries` names, the cup
floor is what the goal needs (`gems_required_goal` Gem Cups, one Gem Cup for
`purple_cup_boss_gauntlet`), each at most the request. A count held at its
floor is set aside and the rest is shared again. When the floors alone do not
fit, the seed is refused as before.

Example: `cup_count: 27`, `crystal_challenge_count: 4` and
`cortex_vortex_track: own_pad`. Cortex Vortex keeps one pad, 26 are left for
31 requested. Quotas 26 * 27 / 31 = 22.65 and 26 * 4 / 31 = 3.35; whole parts
22 and 3, the last pad goes to the cups (0.65 > 0.35): 23 cups and 3 Crystal
Challenges.

The final counts are written back to the options, so the rest of the
generator, the spoiler and later draws see them, and a generator warning names
the requested and the final counts. The plan wire has no new field.
"""
import logging
from fractions import Fraction

from Options import OptionError

PADS = 27


def share(available, requests, floors):
    """Largest remainder share of `available` pads over `requests` (a list of
    non-negative ints, in tie order), with each result between its floor and
    its request. Returns the requests unchanged when they fit, None when the
    floors alone do not."""
    if sum(requests) <= available:
        return list(requests)
    floors = [min(f, r) for f, r in zip(floors, requests)]
    if sum(floors) > available:
        return None
    out = [None] * len(requests)
    open_ = list(range(len(requests)))
    left = available
    while True:
        weight = sum(requests[i] for i in open_)
        quota = {i: Fraction(left * requests[i], weight) if weight else Fraction(0) for i in open_}
        held = [i for i in open_ if quota[i] < floors[i]]
        if not held:
            break
        for i in held:
            out[i] = floors[i]
            left -= floors[i]
            open_.remove(i)
    whole = {i: int(quota[i]) for i in open_}
    spare = left - sum(whole.values())
    for i in sorted(open_, key=lambda i: (-(quota[i] - whole[i]), i))[:spare]:
        whole[i] += 1
    for i in open_:
        out[i] = whole[i]
    return out


def resolve(world, required_tracks, required_arenas):
    """(cups, crystals) for the seed's pad budget, after the required tracks
    (Cortex Vortex `own_pad` included) and the required arenas. Writes the
    options back and warns only when the requests did not fit."""
    o = world.options
    cups, crystals = int(o.cup_count.value), int(o.crystal_challenge_count.value)
    available = PADS - required_tracks
    if available < 0:
        raise OptionError(
            f"CTR content plan: {required_tracks} required track pads (required_entries and cortex_vortex_track: "
            f"own_pad) do not fit the 27 normal pads. List fewer required_entries.")
    if cups + crystals <= available:
        return cups, crystals
    cup_floor = int(o.gems_required_goal.value)
    if o.purple_cup_boss_gauntlet.value:
        cup_floor = max(cup_floor, 1)
    result = share(available, [cups, crystals], [cup_floor, required_arenas])
    if result is None:
        raise OptionError(
            f"CTR content plan: the 27 normal pads cannot hold what must have a pad: {required_tracks} required "
            f"track pads (required_entries and cortex_vortex_track: own_pad), {min(required_arenas, crystals)} "
            f"required arenas and {min(cup_floor, cups)} cups the goal needs. List fewer required_entries.")
    final_cups, final_crystals = result
    o.cup_count.value, o.crystal_challenge_count.value = final_cups, final_crystals
    world.ctr_pad_budget = dict(requested=(cups, crystals), final=(final_cups, final_crystals),
                                required_tracks=required_tracks)
    logging.getLogger("CTR").warning(
        "CTR: %s asks for %d cups and %d Crystal Challenges, but only %d of the 27 normal pads are left after "
        "%d required track pads. The counts are shared out as weights: %d cups and %d Crystal Challenges.",
        world.multiworld.player_name[world.player], cups, crystals, available, required_tracks,
        final_cups, final_crystals)
    return final_cups, final_crystals
