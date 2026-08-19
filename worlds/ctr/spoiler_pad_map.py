"""Human-readable warp-pad destination rows for the spoiler log.

This module is deliberately independent of Archipelago runtime imports so the
identity and shuffled-map contract can be tested directly.
"""


def changed_pad_destination_rows(resolved_map, pad_ids):
    """Return ``(physical_level_id, physical_name, destination_name)`` rows.

    ``resolved_map`` is the complete physical LevelID to destination LevelID
    wire map. Identity entries are omitted, which preserves spoiler output byte
    for byte when destination shuffle made no effective change.
    """
    id_to_name = {
        int(meta["level_id"]): name
        for name, meta in pad_ids.items()
        if "level_id" in meta
    }
    rows = []
    for physical_raw, destination_raw in resolved_map.items():
        try:
            physical = int(physical_raw)
            destination = int(destination_raw)
        except (TypeError, ValueError):
            continue
        if physical == destination:
            continue
        rows.append((
            physical,
            id_to_name.get(physical, f"pad {physical}"),
            id_to_name.get(destination, f"track {destination}"),
        ))
    return sorted(rows)
