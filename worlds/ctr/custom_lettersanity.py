"""Slot-owned custom letter identities; activation awaits certified CTR modes.

No borrowed retail LevelID, mutable package title, or cup-leg number contributes
to the address. Repeated routes to the same seed slot share these identities.

Selection stays keyed by the seed's logical slot. A slot whose track has a
named block (#133) takes its letter and CTR codes from that block instead of
the generic families below (custom_track_ids); the classes here create only
the generic slots' locations and items, and `named_tracks.NAMED_TRACK_CLASS`
creates the named ones.
"""
from .custom_check_namespace import (
    CUSTOM_SLOT_COUNT, LETTERS, custom_check_code, custom_check_name,
)
from .location_class import LocationClass
from BaseClasses import ItemClassification


# Separate from positional data/items.json: these addresses deliberately use
# their own reserved block and must not shift the shipped 0..199 index table.
CUSTOM_LETTER_ITEM_DATA = tuple({
    "name": custom_check_name("letter_item", slot, li),
    "code": custom_check_code("letter_item", slot, li),
    "count": 0,
    "classification": ItemClassification.progression,
} for slot in range(1, CUSTOM_SLOT_COUNT + 1) for li in range(len(LETTERS)))


class CustomLettersanityLocationClass(LocationClass):
    key = "custom_lettersanity"
    display_name = "Custom Track Lettersanity"
    code_blocks = (35020000,)

    def all_locations(self):
        return [(custom_check_name("letter_location", slot, li),
                 custom_check_code("letter_location", slot, li),
                 f"Custom Track {slot}")
                for slot in range(1, CUSTOM_SLOT_COUNT + 1)
                for li in range(len(LETTERS))]

    def location_name(self, slot, letter):
        return custom_check_name("letter_location", slot, LETTERS.index(letter))

    def created_location_names(self, options):
        """None through this class: the content plan creates its custom letter
        checks itself (content_plan). One generator row 12 deleted the legacy
        `custom_tracks` descriptor path that filled this."""
        return []


CUSTOM_LETTERSANITY_CLASS = CustomLettersanityLocationClass()


class CustomCtrChallengeLocationClass(LocationClass):
    key = "custom_ctr_challenge"
    display_name = "Custom Track CTR Challenges"
    code_blocks = (35023000, 35023100)

    def all_locations(self):
        return [(custom_check_name("ctr_location", slot),
                 custom_check_code("ctr_location", slot), f"Custom Track {slot}")
                for slot in range(1, CUSTOM_SLOT_COUNT + 1)]

    def created_location_names(self, options):
        """None through this class: the content plan creates its custom CTR
        Challenge checks itself. One generator row 12 deleted the legacy path."""
        return []


CUSTOM_CTR_CHALLENGE_CLASS = CustomCtrChallengeLocationClass()
