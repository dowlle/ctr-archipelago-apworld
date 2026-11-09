"""Make a synthetic 50-spot capacity apworld for count fuzz arms only.

Never ship this archive. Reviewed placement files in the release are unchanged.
Usage: python box-count-fixture.py input.apworld output.apworld
"""
import json
import sys
import zipfile

with zipfile.ZipFile(sys.argv[1]) as source, zipfile.ZipFile(sys.argv[2], "w", zipfile.ZIP_DEFLATED) as target:
    for member in source.infolist():
        data = source.read(member)
        if member.filename in ("ctr/data/box_spots/retail/CRASH_COVE.json", "ctr/data/box_spots/custom/dk-pass.json"):
            doc = json.loads(data)
            doc["spots"] = [dict(number=n, pos=[n * 10, 0, n * 20], rot_y=0, needs="none")
                            for n in range(1, 51)]
            for spot in doc["spots"]:
                spot["source"] = "builtin" if doc["track"]["kind"] == "retail" and spot["number"] <= 15 else "community"
            data = json.dumps(doc).encode()
        target.writestr(member, data)
