"""Make a synthetic 50-spot capacity apworld for count fuzz arms only.

Never ship this archive. Reviewed placement files in the release are unchanged.
Usage: python box-count-fixture.py input.apworld output.apworld
"""
import hashlib
import json
import sys
import zipfile

ROOT = "ctr/data/box_spots/"
FIXTURES = (ROOT + "retail/POLAR_PASS.json", ROOT + "custom/dk-pass.json")
PROVENANCE = ROOT + "provenance.json"
CATALOG = "ctr/box_spot_catalog.py"

with zipfile.ZipFile(sys.argv[1]) as source, zipfile.ZipFile(sys.argv[2], "w", zipfile.ZIP_DEFLATED) as target:
    provenance = json.loads(source.read(PROVENANCE))
    reviewed = json.dumps(provenance, sort_keys=True, separators=(",", ":")).encode()
    fixtures = {}
    for path in FIXTURES:
        doc = json.loads(source.read(path))
        identity = doc["track"]
        retail = identity["kind"] == "retail"
        track = f"retail:{identity['level_id']}" if retail else f"custom:{identity['track_key']}"
        source_id = f"count-fuzz-fixture-{track}"
        doc["spots"] = [
            dict(number=n, pos=[n * 10, 0, n * 20], rot_y=0, needs="none", source_family="ap_box",
                 provenance=[source_id, n], source="builtin" if retail and n <= 15 else "community")
            for n in range(1, 51)
        ]
        rows = [[s["number"], s["number"], *s["pos"], s["rot_y"]] for s in doc["spots"]]
        provenance[source_id] = dict(
            kind="reviewed_ap_proposal", track=track, pins=doc["track"].get("lev_sha256", []),
            record="Synthetic count fuzz fixture", sha256=hashlib.sha256(json.dumps(rows).encode()).hexdigest(),
            rows=rows,
        )
        fixtures[path] = json.dumps(doc).encode()
    synthetic = json.dumps(provenance, sort_keys=True, separators=(",", ":")).encode()
    fixtures[PROVENANCE] = synthetic
    # This test archive has its own reviewed snapshot. Verify that its input
    # agrees with the release validator before substituting the fixture digest.
    production_approval = hashlib.sha256(reviewed).hexdigest().encode()
    fixture_approval = hashlib.sha256(synthetic).hexdigest().encode()
    validator = source.read(CATALOG)
    if validator.count(production_approval) != 1:
        raise ValueError("Input apworld is missing the reviewed provenance digest")
    fixtures[CATALOG] = validator.replace(production_approval, fixture_approval)
    for member in source.infolist():
        data = fixtures[member.filename] if member.filename in fixtures else source.read(member)
        target.writestr(member, data)
