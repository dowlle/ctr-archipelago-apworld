"""Tizi Madness: Coco Team Racing track 3 by FrostedWombat (A4-96).

THE RULING (2026-11-14 23:03 CET): "I think Tizi Madness should not
appear in Easy and Medium shortcut knowledge seeds and it should require a mask
item. It is a special training track for training Tiziano shortcut. The player
should constantly receive the mask item on this track as a special case".
Clarified by about 23:06 CET: on Itemsanity seeds it requires the Mask item;
on other seeds the game just keeps giving Masks; the slot is "always holding"
a Mask; "everywhere" the track is raced.

What this module owns, on the apworld side:

1. Generation (`leave_out_below_hard`). With `shortcut_knowledge` easy or
   medium the track never enters the seed: its descriptor leaves
   `custom_tracks` before the plan is drawn, so it is no pad, cup leg, boss
   venue or any other use, the same way a box above the chosen shortcut level
   is left out rather than put out of logic. A `required_entries` or
   `track_modes` name for it goes with it. With `hard` nothing changes.
2. Logic (`mask_gated_entries`). With Itemsanity on, every check raced on the
   track also needs the `Mask` weapon item: the region of every pad, Gem Cup
   and boss race that races it is gated on the Mask (content_plan
   create_regions, content_bosses.install). A Gem Cup with a Tizi Madness leg
   gates the whole cup, also its legs before that one: stricter than needed,
   never looser. With Itemsanity off there is no Mask item and no extra term.

The game side (native `ap/ap_tizi_madness.c`) refills the weapon slot with a
Mask while the track is raced, once the Mask item has arrived on an Itemsanity
seed, at once everywhere else.

IDENTITY. The track is recognised by its exact LEV and VRM pins, the files the
client's importer makes from the Coco Team Racing patch (`17e43e10...`,
BIGFILE 47), never by its title or content id: a renamed copy still counts,
and another track that is called "Tizi Madness" does not. The package pin is
not used either, because it changes when the title or credit changes (A4-95).
Native holds the same pair in `include/platform/native_tizi_madness.h`.
"""
import logging

from . import custom_packages, notices

#: The pins of Coco Team Racing track 3 as the importer normalizes it.
LEV_SHA256 = "3e80b47339d243db00acc33d6b7eb9efb15eaf946aa830b1766d56f5b1c15e42"
VRM_SHA256 = "74c00036dd24a34134c76236ae89dba1f3caa4b67bb30ca5717988b8987bf6ce"
#: Where the pins come from, for messages and tests only.
PATCH_SHA256 = "17e43e108b7f732cb8302636f6984a3b0df59df6af517fffab0e860d00209b54"
BIGFILE_INDEX = 47
#: The Itemsanity weapon item the logic asks for.
MASK_ITEM = "Mask"
#: `shortcut_knowledge` from which the track may appear (item_boxes.SK_HARD).
MIN_SHORTCUT_KNOWLEDGE = 2

logger = logging.getLogger("CTR")


def is_tizi_madness(package):
    """Is this admitted descriptor (or plan package) Tizi Madness, by its pins?"""
    if not package:
        return False
    pins = {f.get("role"): f.get("sha256") for f in package.get("files", ())}
    return pins.get("lev") == LEV_SHA256 and pins.get("vrm") == VRM_SHA256


def leave_out_below_hard(world):
    """Rule 1. Drop Tizi Madness from `custom_tracks` below hard shortcut
    knowledge, with the names other options give it. A descriptor that does
    not pass admission is kept as it is, so the normal admission error names
    it. Returns the ids left out (empty when nothing changed)."""
    o = world.options
    if int(o.shortcut_knowledge.value) >= MIN_SHORTCUT_KNOWLEDGE:
        return []
    kept, dropped, names = [], [], set()
    for raw in o.custom_tracks.value:
        try:
            package = custom_packages.admit(raw, "custom_tracks")
        except custom_packages.PackageError:
            kept.append(raw)
            continue
        if is_tizi_madness(package):
            dropped.append(package["id"])
            names.update((package["display_name"], package["content_id"]))
        else:
            kept.append(raw)
    if not dropped:
        return []
    o.custom_tracks.value = kept
    o.required_entries.value = [n for n in o.required_entries.value if n not in names]
    o.track_modes.value = {k: v for k, v in o.track_modes.value.items() if k not in names}
    world.ctr_tizi_madness_left_out = dropped
    notices.note_ignored(world, "Tizi Madness in custom_tracks (it needs shortcut_knowledge hard)")
    return dropped


def tizi_track_ids(plan):
    """Plan track ids that are Tizi Madness."""
    packages = {p["id"]: p for p in plan.get("packages", ())}
    return {t["id"] for t in plan.get("tracks", ())
            if t.get("package_id") is not None and is_tizi_madness(packages.get(t["package_id"]))}


def mask_gated_entries(plan):
    """Rule 2. Entry ids whose race is on Tizi Madness: a track pad's entry,
    a boss race on it, or a Gem Cup or boss cup with it as a leg. Empty without
    Itemsanity, because then the game needs no item to give the Mask."""
    if not plan.get("global_checks", {}).get("itemsanity"):
        return frozenset()
    tracks = tizi_track_ids(plan)
    if not tracks:
        return frozenset()
    out = set()
    for entry in plan.get("entries", ()):
        if entry.get("track_id") in tracks or any(leg.get("track_id") in tracks for leg in entry.get("legs", ())):
            out.add(entry["id"])
    return frozenset(out)


def mask_term(world):
    from . import logic_terms
    return logic_terms.Has(MASK_ITEM, 1, world.player)
