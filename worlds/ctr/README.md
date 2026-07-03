# Crash Team Racing (CTR Archipelago)

An [Archipelago](https://archipelago.gg) Multiworld world for **Crash Team Racing (PSX, 1999)**.

This world targets the native PC client [`ctr-native-ap`](https://github.com/dowlle/ctr-native-ap), a build of the CTR-tools decompilation that connects to Archipelago directly, in-process. No emulator, no ROM patching. The world handles all randomization (warp-pad requirements and destination shuffle, two-stage requirements, boss/door/gem-cup gating, goals) and hands the client a per-seed configuration through slot data.

The randomization design builds on Icebound777's CTR randomizer (MIT), and this project carries the native path forward with his blessing. The foundational work, and the credit for it, stays with him and Taor.

**Status: in development, not yet released.** The code is public for collaboration and transparency; there is no supported player-facing release yet.

---

## AI Usage Disclosure

I want to be upfront about how this project is built. CTR Archipelago is developed with AI assistance, specifically Anthropic's Claude, through Claude Code.

**What AI does.** A substantial part of the code is written or co-written with AI under my direction: the apworld's randomization and generation logic, the native AP-client integration in the ctr-native decomp, and debugging and code-review passes. AI also helps me keep the project backlog organised.

**What AI does not do.** There is no AI-generated art anywhere in this project. Every tracker icon and in-game marker is rendered from the game's own 3D models. No generated textures, no generated logos, no generated models.

**How I make sure it's actually correct.** AI writes a lot of the code, but nothing ships unreviewed or unverified:

- Every apworld release passes a full run of Eijebong's Archipelago fuzzer: 10 out of 10 check categories clean across roughly 14,000 randomized generations. Nothing ships red. This is the same bar I hold my other apworlds to, and I'd recommend it to any apworld developer, AI-assisted or not.
- I test every native build in-game myself, on real generated seeds, before it goes out. Automated checks catch generation bugs; I catch the "looks fine, plays broken" ones by actually playing them.
- I verify instead of guessing. Gating and solvability behaviour is checked against the game's actual code, against generation with accessibility set to full, and in-game, and reverted if it doesn't hold up.
- The architecture is written down and human-reviewed. The project has a formal specification and an apworld-to-client data contract, which I went through section by section on 2026-07-01. I don't merge code I haven't understood from a principled perspective.

**Why I use AI, honestly.** AI lets me actually finish the ideas I have. I have ADHD, and left to my own devices most of my projects would never reach a working state. I'm not thrilled that I can't do all of this unaided, but I'd rather ship something complete and playable than ship nothing at all. I don't pretend AI has no downsides, and I don't want to wave those away. Using it is a considered choice, not a careless one.

**Credit.** The randomization design is built on Icebound777's CTR randomizer (MIT), and CTR-AP carries the ctr-native path forward with his blessing. The foundational work, and the credit for it, stays with him.

Now you know what you're getting. If AI-assisted development is a dealbreaker for you, that's a fair call to make with the facts in front of you.
