"""Human-readable warp-pad destination rows for the spoiler log.

This module is deliberately independent of Archipelago runtime imports so the
identity and shuffled-map contract can be tested directly.
"""


def changed_pad_destination_rows(resolved_map, pad_ids, custom_destinations=None):
    """Return ``(physical_level_id, physical_name, destination_name)`` rows.

    ``resolved_map`` is the complete physical LevelID to destination LevelID
    wire map. Identity entries are omitted, which preserves spoiler output byte
    for byte when destination shuffle made no effective change.

    ``custom_destinations`` optionally maps a displaced destination LevelID to
    ``(track_id, track_title)`` -- the effective-destination representation
    for a custom replacement. Every physical pad whose resolved destination is
    such a LevelID then reports the custom track as the effective load,
    retaining the displaced destination (named from ``pad_ids``) in the same
    row. The displaced cup's own pad is included even at identity, because
    native still serves the custom track there. An absent (or empty) mapping
    leaves the output byte-identical to the pre-custom-tracks spoiler.
    """
    id_to_name = {
        int(meta["level_id"]): name
        for name, meta in pad_ids.items()
        if "level_id" in meta
    }
    custom = dict(custom_destinations or {})
    rows = []
    for physical_raw, destination_raw in resolved_map.items():
        try:
            physical = int(physical_raw)
            destination = int(destination_raw)
        except (TypeError, ValueError):
            continue
        if physical == destination and physical not in custom:
            continue
        if destination in custom:
            _track_id, track_title = custom[destination]
            displaced_name = id_to_name.get(destination, f"pad {destination}")
            destination_name = f"{track_title} (replaces {displaced_name})"
        else:
            destination_name = id_to_name.get(destination, f"track {destination}")
        rows.append((
            physical,
            id_to_name.get(physical, f"pad {physical}"),
            destination_name,
        ))
    return sorted(rows)
