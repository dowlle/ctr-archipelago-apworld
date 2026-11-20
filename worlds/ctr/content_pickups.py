"""Repeatable fill routes for optional venue pickups (A6-16c).

Wire routes still describe physical awards, including an early Oxide 1 pickup.
Only the fill rule drops that one-shot encounter. Old plans keep their rules.
Lap, victory and global checks have independent award guarantees.

A6-48 (ruling of 2026-11-20, "Build for alpha6"): a venue whose only
allowed route is the Final Challenge gets no checks of its own. With
`final_only_venue_v1`, a lap check whose every route is the Final Challenge,
and an optional pickup check (the families above) with no route besides the
First and Final Challenges, leave the plan. A check with another route stays,
keeps its Final Challenge route and may still be collected during the final.
The final's win and the venue's package stay. Plans without the feature keep
their checks.
"""
FEATURE = "repeatable_pickups_v1"
FINAL_FEATURE = "final_only_venue_v1"
FIRST = "encounter/garage:4/0"
FINAL = "encounter/garage:4/1"
KINDS = ("weapon_crate", "wumpa_crate", "wumpa_fruit", "wumpa")
LAP_KIND = "lap"


def enabled(plan):
    return FEATURE in plan["required_features"]


def final_enabled(plan):
    return FINAL_FEATURE in plan["required_features"]


def repeatable(route):
    return route["encounter_id"] != FIRST


def logic_routes(check, active):
    if active and check["kind"] in KINDS and check["owner"] != "global":
        return [r for r in check["routes"] if repeatable(r)]
    return check["routes"]


def omit_unrepeatable(checks):
    return [c for c in checks if c["kind"] not in KINDS or c["owner"] == "global"
            or logic_routes(c, True)]


def final_only(check):
    """Is `check` a venue check that only the Final Challenge reaches (A6-48)?
    A pickup's First Challenge route does not count (A6-16c); a lap's does."""
    if check["owner"] == "global" or check["kind"] not in KINDS + (LAP_KIND,):
        return False
    skip = (FINAL,) if check["kind"] == LAP_KIND else (FIRST, FINAL)
    return bool(check["routes"]) and all(r["encounter_id"] in skip for r in check["routes"])


def omit_final_only(checks):
    return [c for c in checks if not final_only(c)]
