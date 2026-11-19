"""Repeatable fill routes for optional venue pickups (A6-16c).

Wire routes still describe physical awards, including an early Oxide 1 pickup.
Only the fill rule drops that one-shot encounter. Old plans keep their rules.
Lap, victory and global checks have independent award guarantees.
"""
FEATURE = "repeatable_pickups_v1"
FIRST = "encounter/garage:4/0"
KINDS = ("weapon_crate", "wumpa_crate", "wumpa_fruit", "wumpa")


def enabled(plan):
    return FEATURE in plan["required_features"]


def repeatable(route):
    return route["encounter_id"] != FIRST


def logic_routes(check, active):
    if active and check["kind"] in KINDS and check["owner"] != "global":
        return [r for r in check["routes"] if repeatable(r)]
    return check["routes"]


def omit_unrepeatable(checks):
    return [c for c in checks if c["kind"] not in KINDS or c["owner"] == "global"
            or logic_routes(c, True)]
