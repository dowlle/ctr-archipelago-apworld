# Crash Team Racing Setup Guide

This guide covers setting up Crash Team Racing (PS1, 1999) for Archipelago. CTR
runs as a native PC port with the Archipelago client built directly into it:
no emulator and no ROM patching. The client connects to the server, receives
items, locks and unlocks warp pads, boss garages, doors and gem cups per seed,
and sends your location checks and goal.

## Required Software

- The **CTR Archipelago client**, `ctr_native_ap` (Windows `.exe` or Linux
  binary), from the [client Releases page](https://github.com/dowlle/ctr-native-ap/releases).
- The **CTR apworld** (`ctr.apworld`), from the same Releases page. Only the
  person who generates the multiworld needs this.
- A legally obtained **NTSC-U (North American)** disc image of Crash Team
  Racing. A `.cue` plus `.bin`, a single `.bin`, or a `.chd` all work. Only the
  North American release is supported: PAL (European) and Japanese discs are
  detected and refused. This project ships no game data; you supply it from your
  own disc.
- **Python 3.8 or newer**, only for the recommended asset extractor below. If
  your image is a `.chd`, you also need the `chdman` tool (it ships with the MAME
  tools) on your PATH.
- The **Archipelago installation**, if you are the one generating the
  multiworld, from the [Archipelago releases page](https://github.com/ArchipelagoMW/Archipelago/releases).

## Installing the apworld (generation only)

Only the person generating the multiworld needs this step. Double-click
`ctr.apworld`, or place it in the `custom_worlds` folder of your Archipelago
installation, so the generator can build CTR seeds.

## Configuring your YAML file

### What is a YAML file and why do I need one?

Your YAML file contains a set of configuration options which provide the
generator with information about how it should generate your game. Each player
of a multiworld provides their own YAML file. This lets each player enjoy an
experience customized for their taste, and different players in the same
multiworld can all have different options.

### Where do I get a YAML file?

After installing the apworld, open the Archipelago Launcher, choose **Generate
Template Options**, and pick Crash Team Racing to get the template YAML. You can
also customize options on the
[Crash Team Racing options page](/games/Crash%20Team%20Racing/player-options).

Set your slot name (spelled exactly as it will appear in the room) and your
options, then hand the YAML to whoever generates the multiworld. As a player you
only need the YAML you submitted, the client set up below, and your slot name.

A few options worth knowing about: with randomized warp pad requirements,
`two_stage_density` controls how many trophy pads carry a real second-stage
gate (an extra requirement on the pad's CTR Challenge and Time Trial beyond
the Trophy Race itself), from `off` to `deep`; and `trap_fill_percentage` adds
trap items to the pool — they are all named with a "... Trap" suffix (for
example "Icy Road Trap"), so you can tell at a glance when one is headed your
way. Every option is documented in the template YAML.

## Setting up the game client

### Step 1: get the game executable

Download `ctr_native_ap` for your platform from the
[client Releases page](https://github.com/dowlle/ctr-native-ap/releases) and put
it in a folder of its own, for example a folder called `CTR-AP`. The next steps
add the game data and your server settings next to it.

### Step 2: add your game assets

You have two options. The extractor is recommended.

**Recommended: extract the assets.** The extractor reads your disc image and
copies out only the files the game needs into an `assets` folder, checking the
region and that nothing is missing. From the folder that holds the executable,
run:

```
python extract_assets.py "path/to/your/CTR.cue"
```

You can also point it at a `.bin` or a `.chd`. By default it writes an `assets`
folder in the current directory; add `--out "path/to/CTR-AP/assets"` to send it
elsewhere. When it finishes you should have:

```
CTR-AP/
  ctr_native_ap.exe
  assets/
    BIGFILE.BIG
    SOUNDS/KART.HWL
    TEST.STR
    XA/ENG.XNF
    XA/ENG/EXTRA/S00.XA ... S05.XA
    XA/ENG/GAME/S00.XA ... S20.XA
    XA/MUSIC/S00.XA ... S01.XA
```

**Alternative: one raw file, no extractor.** The game can also read the raw disc
image directly. Rename your NTSC-U `.bin` to `ctr-u.bin` and place it in the
`assets` folder:

```
CTR-AP/
  ctr_native_ap.exe
  assets/
    ctr-u.bin
```

This must be the common single-track raw PlayStation BIN layout (MODE2/2352
sectors). A cooked 2048-byte `.iso` does not carry the audio and video sector
data the game needs, so it will not work. This path skips the region check and
uses more disk space than the extracted folder, which is why the extractor is
recommended.

### Step 3: connect to your room

Launch the executable. On a first start with no saved connection the game boots
to the main menu and shows that it is not connected. Go to **OPTIONS →
Connection**, and type your room details with your keyboard:

- **Server**: the address of your room, for example `archipelago.gg:38281`
  (the port is on your room page). Secure connections (`wss://`) are used
  automatically for hosted rooms; for a server on your own machine use
  `ws://localhost:38281` or just `localhost:38281`.
- **Slot**: your player name in the room, spelled exactly as it appears there.
- **Password**: the room password, or leave it blank if there is none.

Select **Connect**. The status line on the same screen shows the connection
state (Connecting… / Connected / an error message). Your settings are saved to
`config.ini` next to the executable, and the game reconnects automatically on
later launches.

**Alternative: config file.** If you prefer a text file, copy
`ap-config.example.txt` to `ap-config.txt` next to the executable and set
`uri`, `slot`, and `password` there; the game reads it at startup. Values saved
from the in-game Connection screen (`config.ini`) take precedence when both
exist. The example file also documents a few optional quality of life toggles
(`skip_hints`, `map_flash`).

## Troubleshooting

- **"Missing or incomplete assets" at startup:** the `assets` folder is not next
  to the executable, or a file did not extract. Re-run the extractor and make
  sure the `assets` folder sits in the same directory as the executable.
- **"PAL is not supported yet" from the extractor:** your disc is the European
  release. You need the North American (NTSC-U) disc, whose boot id starts with
  SCUS.
- **"This is a .chd image, which needs the chdman tool":** install `chdman` (it
  ships with the MAME tools) and make sure it is on your PATH, or convert the
  `.chd` to `.bin`/`.cue` yourself and run the extractor on the `.cue`.
- **"does not look like a PlayStation disc image":** you likely pointed the tool
  at the wrong file (a zip, a folder, or a cooked `.iso`). Use the raw `.bin`,
  `.cue`, or `.chd` of the disc.
- **The game window opens but there is no music or the intro video is black:**
  your image was probably a cooked 2048-byte `.iso`, which drops the XA and STR
  sector data. Re-dump or re-obtain the disc as a raw MODE2/2352 image.
- **Cannot connect to the server:** check the server address, slot name, and
  password in **OPTIONS → Connection** (the status line there shows the error
  reason) — or in `ap-config.txt` if you use the config file instead. The slot
  name must match the room exactly. Note that settings saved from the in-game
  screen (`config.ini`) override `ap-config.txt`.

## Joining a multiworld

New to Archipelago itself? Start with the
[Archipelago tutorials](https://archipelago.gg/tutorial/).
