import json, os, pathlib, zipfile, hashlib, sys

file_name = "ctr"
world_directory = os.path.join("worlds", file_name)
GAME = "Crash Team Racing"

from Utils import read_apignore, local_path
from worlds import AutoWorldRegister
from worlds.Files import APWorldContainer

worldtype = AutoWorldRegister.world_types[GAME]

with open(os.path.join(world_directory, "archipelago.json"), encoding="utf-8") as f:
    manifest = json.load(f)

global_apignores = read_apignore(local_path("data", "GLOBAL.apignore"))
assert global_apignores, "no global apignore"
local_ig = read_apignore(pathlib.Path(world_directory, ".apignore"))
apignores = global_apignores + local_ig if local_ig else global_apignores

out_dir = "/home/stef/apworld-fuzzer/stage-020-54-209-charphase"
os.makedirs(out_dir, exist_ok=True)
zip_path = os.path.join(out_dir, "ctr.apworld")
if os.path.exists(zip_path):
    os.remove(zip_path)

apworld = APWorldContainer(zip_path)
apworld.game = worldtype.game
manifest.update(apworld.get_manifest())
apworld.manifest_path = os.path.join(file_name, "archipelago.json")

members = []
excluded_test = []
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
    for file in sorted(apignores.match_tree_files(world_directory, negate=True)):
        parts = pathlib.PurePath(file).parts
        if parts and parts[0] == "test":
            excluded_test.append(str(pathlib.PurePath(file_name, file)))
            continue
        arc = str(pathlib.PurePath(file_name, file))
        zf.write(pathlib.Path(world_directory, file), arc)
        members.append(arc)
    zf.writestr(apworld.manifest_path, json.dumps(manifest))
    members.append(apworld.manifest_path)

data = open(zip_path, "rb").read()
print("ZIP_PATH", zip_path)
print("SHA256", hashlib.sha256(data).hexdigest())
print("BYTES", len(data))
print("MEMBER_COUNT", len(members))
print("EXCLUDED_TEST_COUNT", len(excluded_test))
print("---MEMBERS---")
for m in sorted(members):
    print(m)
print("---EXCLUDED_TEST---")
for m in sorted(excluded_test):
    print(m)
assert not any("/test/" in m or m.startswith("ctr/test/") for m in members), "TEST LEAKED INTO ARTIFACT"
print("ASSERT_NO_TEST_MEMBERS OK")
