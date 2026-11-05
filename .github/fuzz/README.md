# CTR world CI

`.github/workflows/ctr-world.yml` runs `pytest worlds/ctr`, packs `ctr.apworld` and fuzzes the packed file. The fuzz arms are defined once, in `ctr-world-matrix.yml`. `.github/scripts/ctr_fuzz_tiers.py` picks how many of them a run gets.

## Fuzz tiers

| Tier | Arms | When |
|---|---|---|
| none | no fuzz; pytest and pack still run | a pull request that changes only safe paths |
| pr | the 12 arms in `PR_ARMS` | every other pull request, and every push to `dev/**` |
| full | every arm in `ctr-world-matrix.yml` | pushes to `main`, `release/**` and `ci/**`, the nightly dev run, manual runs, and pull requests with the `full-fuzz` label |

Safe paths are `worlds/ctr/solo/`, `worlds/ctr/docs/`, `worlds/ctr/test/`, any `.md` file, and the version files `worlds/ctr/version.py`, `worlds/ctr/archipelago.json` and `worlds/ctr/datapackage_manifest.json`. A pull request is classified on its whole file list, so one generation file anywhere in it selects the pr tier. A push is never tier none.

The pr tier covers each generation family at least once:

| Family | Arms |
|---|---|
| default | `canonical-default`, `default`, `no-restrictive-starts` |
| content plan | `content-plan-vanilla`, `content-plan-full`, `content-plan-132` |
| cups | `gem-cups-7-random` |
| bosses | `content-plan-bosses` |
| pads | `pads-all-ut` (every pad overlay at once, through Universal Tracker) |
| Universal Tracker | `check-ut` |
| determinism | `check-determinism`, `check-static-output` |

The classifier's own tests fail if a family loses its last arm. A change that only matters to an arm outside the pr tier (for example one pads overlay or a gem-cups meta) should get the `full-fuzz` label.

## The full-fuzz label

Adding `full-fuzz` to a pull request reruns it on the full tier straight away and cancels its running pr-tier checks. Every later push to that pull request stays on the full tier until the label is removed. Other labels start no checks and cancel nothing.

## Nightly and before a tag

- The schedule (03:17 UTC, on `main`) only dispatches a full run on `dev/custom-pad-0.3.0`. GitHub runs schedules from the default branch, so the nightly starts once this workflow is on `main`. Until then, start it by hand.
- A failed nightly run opens one issue titled "Nightly CTR fuzz failure", with the failing arms and, for each failed generation, its run number, YAML file and error line (the pinned fuzzer draws a random Archipelago seed and does not log it); later failures add a comment to that issue while it is open. The failing YAMLs are in the run's `fuzz-failure-<arm>` artifacts.
- Before tagging, run the CTR world workflow by hand (Run workflow, or `gh workflow run ctr-world.yml --ref <branch>`) on the commit to tag, and use that run's id as `apworld_run_id` in the native `release-prepare` workflow.
- `.github/workflows/ctr-tag-guard.yml` checks a pushed `v*` tag: it fails unless the tagged commit has a CTR world run in which pytest, pack and every matrix arm passed. A pr-tier run never counts. Run it by hand on a branch to check that branch's head before tagging.

## Required check

`ctr-world summary` passes only when every job its tier needs passed. Neither repository has branch protection today; if it is turned on, require only `ctr-world summary` from this workflow, not the per-arm checks, because pr-tier and none-tier runs skip arms.
