"""Shared infrastructure for CTR's optional location classes (issue #176).

0.2.0 adds three more optional location classes on top of the podium rungs that
already shipped: relic-race perfect checks (#49), item-box locations (#109) and
lettersanity (#148), plus itemsanity (#145). They are the same feature wearing
different hats: a frozen name superset registered unconditionally into the
datapackage, a per-seed subset created from options, and a native hook that
fires a check on an in-race event.

This module is that shape, extracted BEFORE the third and fourth instances are
written. It adds no locations, changes no behaviour, and settles no design
question about the classes themselves. `podium.py` is the only member today.

WHAT A LOCATION CLASS OWNS
--------------------------
A `LocationClass` subclass answers exactly two questions and gets the rest for
free:

  * `all_locations()` -- the FROZEN `(name, code, region)` superset, independent
    of options. This is what `Locations.py` folds into `CTR_LOCATION_IDS` at
    import, so it is a permanent datapackage commitment: names and codes here
    must never move once shipped.
  * `created_location_names(options)` -- the names THIS seed creates, a subset of
    the superset. Single source consumed by `Regions.py` (creation), `Rules.py`
    (reachability) and `__init__.fill_slot_data` (the native fan-out array) so
    they can never disagree about which locations a seed has.

Everything else -- the name/code index, `code_for`, `is_enabled`,
`created_locations` in superset order -- is derived here, once, instead of
copied per class.

WHAT THIS DELIBERATELY DOES NOT DO
----------------------------------
It does not model region creation, rules, or the slot_data block shape. Those
are genuinely per-class today (podium builds a dead-end `"<track>: Podium"`
region with rule-True entrances; a global class like #145 itemsanity has no
per-track structure at all), and inventing one shape for them before the second
real instance exists would be fitting a framework to a sample of one.

It also does not decide exclusion semantics. `exclude_locations` /
`priority_locations` handling is issue #28 and is unruled; classes here behave
exactly as their locations behaved before the extraction, which is: AP's normal
handling, plus `__init__._exclude_goal_location` for the goal locations. The
registry never caches created-location state, so nothing here can resurrect a
location that generation removed.

DOCSTRING CONVENTION (the fourth thing every class copies)
----------------------------------------------------------
Every class module opens with a docstring that names, in this order: what the
class checks and where the signal comes from; which side owns the semantics
(apworld vs native); a DATAPACKAGE STABILITY paragraph naming every code block
the class claims and stating that the superset registers unconditionally; and,
until the 0.2.0 name freeze lands (#177), a FROZEN-NAME WARNING saying the names
are permanent after the bump. `podium.py` and `relic_perfect.py` both already do
this; it is written down here so the third and fourth do too.
"""
from typing import Dict, Iterable, List, Mapping, Sequence, Set, Tuple

# (location name, AP location code, AP region name)
LocationEntry = Tuple[str, int, str]


class LocationClass:
    """One optional CTR location class.

    Subclasses set `key` and implement `all_locations()` and
    `created_location_names(options)`. `location_name()` is conventional but its
    signature is class-specific (podium keys on (track, rung); a global class
    keys on one identifier), so it is not pinned here.
    """

    #: stable internal identifier, also the registry key. Never user-visible.
    key: str = ""
    #: human label for build notes and (future) location name groups.
    display_name: str = ""
    #: every AP code block this class claims. Documentation for the freeze
    #: (#177) and asserted against `all_locations()` by the infra tests.
    code_blocks: Tuple[int, ...] = ()

    # ------------------------------------------------------------------ required

    def all_locations(self) -> List[LocationEntry]:
        """The frozen `(name, code, region)` superset, independent of options."""
        raise NotImplementedError

    def created_location_names(self, options) -> List[str]:
        """The location names THIS seed creates. Must be a subset of the
        superset's names. Order is the class's own; `created_locations()`
        re-imposes superset order on top of it."""
        raise NotImplementedError

    def location_name(self, *key) -> str:
        """The AP location name for a class-specific key."""
        raise NotImplementedError

    # ------------------------------------------------------------------- derived

    def names(self) -> Tuple[str, ...]:
        """Superset names in superset order."""
        self._build_index()
        return self._names

    def name_to_code(self) -> Dict[str, int]:
        """Superset name -> AP code, in superset order."""
        self._build_index()
        return dict(self._name_to_code)

    def name_to_region(self) -> Dict[str, str]:
        """Superset name -> AP region name, in superset order."""
        self._build_index()
        return dict(self._name_to_region)

    def code_for(self, *key) -> int:
        """The AP code for a class-specific key, resolved through the superset
        rather than by re-deriving the block arithmetic at the call site."""
        self._build_index()
        return self._name_to_code[self.location_name(*key)]

    def is_enabled(self, options) -> bool:
        """Does this seed create ANY of this class's locations? A class whose
        master toggle is on but whose sub-toggles all say no is NOT enabled: it
        contributes nothing, which is the property callers actually want."""
        return bool(self.created_location_names(options))

    def created_locations(self, options) -> List[LocationEntry]:
        """This seed's created entries, in SUPERSET order regardless of the order
        `created_location_names` returned them in. Deterministic per (class,
        options) by construction, because the superset order is frozen.

        Raises if the class minted a name outside its own superset -- that is a
        location with no datapackage entry, which fails later and further away.
        """
        self._build_index()
        created = set(self.created_location_names(options))
        unknown = created - set(self._names)
        if unknown:
            raise ValueError(
                f"location class {self.key!r} created {len(unknown)} name(s) that "
                f"are not in its frozen superset: {sorted(unknown)[:5]}. Every "
                "created location must be registered in all_locations(), or it "
                "has no datapackage id."
            )
        return [entry for entry in self.all_locations() if entry[0] in created]

    def location_name_groups(self) -> Dict[str, Set[str]]:
        """Location name groups this class contributes to the datapackage.

        Default: none. `location_name_groups` is part of the datapackage payload
        AP checksums, so adding a group is an additive datapackage change, not a
        free label -- classes opt in deliberately. Members must be names from
        this class's own superset; the registry enforces that.
        """
        return {}

    # -------------------------------------------------------------------- internal

    def _build_index(self) -> None:
        if getattr(self, "_index_built", False):
            return
        entries = self.all_locations()
        names: List[str] = []
        name_to_code: Dict[str, int] = {}
        name_to_region: Dict[str, str] = {}
        seen_codes: Dict[int, str] = {}
        for name, code, region in entries:
            if name in name_to_code:
                raise ValueError(
                    f"location class {self.key!r} registers the name {name!r} twice"
                )
            if code in seen_codes:
                raise ValueError(
                    f"location class {self.key!r} registers code {code} twice "
                    f"({seen_codes[code]!r} and {name!r})"
                )
            names.append(name)
            name_to_code[name] = code
            name_to_region[name] = region
            seen_codes[code] = name
        self._names: Tuple[str, ...] = tuple(names)
        self._name_to_code = name_to_code
        self._name_to_region = name_to_region
        self._index_built = True

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<LocationClass {self.key!r} ({len(self.all_locations())} locations)>"


class LocationClassRegistry:
    """The registered location classes, in registration order.

    Registration order IS the datapackage order for every location a class
    contributes, so it must be deterministic and append-only: a new class goes at
    the END of the registration list in `Locations.py`, never in the middle.
    Codes are explicit per class (unlike item ids, which are positional -- see
    #168), so a reorder would not renumber anything; keeping the order stable
    keeps `location_name_to_id` byte-stable anyway, which is what makes a
    datapackage manifest diff (#177) readable.
    """

    def __init__(self) -> None:
        self._classes: List[LocationClass] = []
        self._by_key: Dict[str, LocationClass] = {}
        self._name_owner: Dict[str, str] = {}
        self._code_owner: Dict[int, str] = {}
        self._group_owner: Dict[str, str] = {}

    # ------------------------------------------------------------- registration

    def register(self, location_class: LocationClass) -> LocationClass:
        """Register a class, validating it against everything already registered.

        Re-registering the SAME instance is a no-op (module reload in a test run
        must not explode); registering a DIFFERENT class under a taken key is an
        error.
        """
        key = getattr(location_class, "key", "")
        if not key or not isinstance(key, str):
            raise ValueError(
                f"{location_class!r} must set a non-empty string `key`"
            )
        existing = self._by_key.get(key)
        if existing is not None:
            if existing is location_class:
                return location_class
            raise ValueError(
                f"location class key {key!r} is already registered by {existing!r}"
            )

        # forces the class's own duplicate-name / duplicate-code checks
        entries = location_class.all_locations()
        location_class.name_to_code()

        for name, code, _region in entries:
            owner = self._name_owner.get(name)
            if owner is not None:
                raise ValueError(
                    f"location class {key!r} claims the name {name!r}, already "
                    f"registered by {owner!r}"
                )
            owner = self._code_owner.get(code)
            if owner is not None:
                raise ValueError(
                    f"location class {key!r} claims code {code}, already "
                    f"registered by {owner!r}"
                )

        own_names = set(location_class.names())
        for group, members in location_class.location_name_groups().items():
            owner = self._group_owner.get(group)
            if owner is not None:
                raise ValueError(
                    f"location class {key!r} declares the location name group "
                    f"{group!r}, already declared by {owner!r}. Two classes "
                    "sharing a group name would silently merge in the "
                    "datapackage."
                )
            stray = set(members) - own_names
            if stray:
                raise ValueError(
                    f"location class {key!r} puts {sorted(stray)[:5]} in group "
                    f"{group!r}, but they are not in its own superset"
                )

        for name, code, _region in entries:
            self._name_owner[name] = key
            self._code_owner[code] = key
        for group in location_class.location_name_groups():
            self._group_owner[group] = key
        self._by_key[key] = location_class
        self._classes.append(location_class)
        return location_class

    def assert_disjoint_from(self, existing: Mapping[str, int], label: str) -> None:
        """Guard the registered classes against the STATIC location table.

        Class codes live in additive blocks above the static `data/locations.json`
        range; this is the assertion of that, run at import so a block collision
        is a hard failure at load rather than a silently overwritten id.
        """
        static_codes = {code: name for name, code in existing.items()
                        if code is not None}
        for name, code, _region in self.all_locations():
            if name in existing:
                raise ValueError(
                    f"location class {self._name_owner[name]!r} claims the name "
                    f"{name!r}, which {label} already defines"
                )
            clash = static_codes.get(code)
            if clash is not None:
                raise ValueError(
                    f"location class {self._name_owner[name]!r} claims code "
                    f"{code} for {name!r}, which {label} already uses for "
                    f"{clash!r}"
                )

    # ------------------------------------------------------------------ read side

    @property
    def classes(self) -> Tuple[LocationClass, ...]:
        return tuple(self._classes)

    def get(self, key: str) -> LocationClass:
        return self._by_key[key]

    def __contains__(self, key: object) -> bool:
        return key in self._by_key

    def __len__(self) -> int:
        return len(self._classes)

    def __iter__(self):
        return iter(self._classes)

    def all_locations(self) -> List[LocationEntry]:
        """Every registered class's frozen superset, concatenated in registration
        order. This is the datapackage contribution and its order is stable."""
        out: List[LocationEntry] = []
        for location_class in self._classes:
            out.extend(location_class.all_locations())
        return out

    def name_to_code(self) -> Dict[str, int]:
        return {name: code for name, code, _region in self.all_locations()}

    def location_name_groups(self) -> Dict[str, Set[str]]:
        """The merged location name groups. Empty while no class declares any,
        which keeps the datapackage identical to the pre-extraction one."""
        merged: Dict[str, Set[str]] = {}
        for location_class in self._classes:
            for group, members in location_class.location_name_groups().items():
                merged[group] = set(members)
        return merged

    # ------------------------------------------------------------- per-seed side

    def active(self, options) -> Tuple[LocationClass, ...]:
        """The classes that create at least one location for this seed, in
        registration order."""
        return tuple(c for c in self._classes if c.is_enabled(options))

    def created_locations(self, options) -> List[LocationEntry]:
        """Every entry created this seed, registration order then superset
        order."""
        out: List[LocationEntry] = []
        for location_class in self._classes:
            out.extend(location_class.created_locations(options))
        return out
