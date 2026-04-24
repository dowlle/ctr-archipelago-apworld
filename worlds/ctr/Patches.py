"""
CTR Archipelago patch extensions.

Adds a `regenerate_ecc` procedure step to the CTR apworld that regenerates
EDC (Error Detection Code) and ECC (Error Correction Code) data for modified
CD-ROM sectors after bsdiff4 and token writes.

This is needed because the CTR base_patch.bsdiff4 modifies bytes in sector 26
(LBA 176), and the apply_tokens step writes seed-specific data into the same
sector's user-data region. Both leave the sector's EDC/ECC stale. BizHawk's
PSX cores (Octoshock/Nymashock) validate EDC/ECC strictly during early disc
boot and freeze on the Adventure Mode loading screen when they see a mismatch.
DuckStation is lenient and boots the same stale-ECC ROM without issue.

Running EDC+ECC regeneration as a final procedure step produces a BizHawk-
loadable ROM with no ambient emulator-config tweaks required.

TEMPORARY IMPLEMENTATION NOTE (Appie, 2026-04-24):
This initial version shells out to EDCRE v1.1.0 (alex-free, GPLv2) for the
actual EDC+ECC computation. That is fine for LOCAL validation of the
procedure-step architecture, but is NOT suitable for upstreaming or general
distribution because:

  1. It depends on an external binary being on a known path.
  2. EDCRE is GPLv2; bundling it inside an (typically MIT-licensed) apworld
     has license-compatibility implications.
  3. It only works on Windows/x86_64 as shipped in `tools/edcre/`.

A pure-Python MODE2_FORM1 EDC+ECC regenerator should replace this before any
upstream PR. The reference algorithm is documented in ECMA-130; the canonical
C implementation is in CDRDAO's `lec.c` (GPLv2). EDCRE output on our test ROM
provides a known-good byte-for-byte comparison baseline for validation.
"""
import os
import shutil
import subprocess
import tempfile
from typing import ClassVar

from worlds.Files import APPatchExtension, APProcedurePatch


# Local path where EDCRE was placed during Track B validation.
# Override via env var CTR_EDCRE_PATH if the binary lives elsewhere.
_DEFAULT_EDCRE_PATH = (
    r"D:\pythonProjects\ctr-archipelago\tools\edcre\edcre-v1.1.0-windows-x86_64-static\edcre.exe"
)


def _locate_edcre() -> str:
    """Find the EDCRE binary to use. Returns an absolute path or raises."""
    override = os.environ.get("CTR_EDCRE_PATH")
    if override and os.path.isfile(override):
        return override
    if os.path.isfile(_DEFAULT_EDCRE_PATH):
        return _DEFAULT_EDCRE_PATH
    on_path = shutil.which("edcre") or shutil.which("edcre.exe")
    if on_path:
        return on_path
    raise FileNotFoundError(
        "EDCRE binary not found. Set CTR_EDCRE_PATH env var, install edcre on PATH, "
        f"or place it at {_DEFAULT_EDCRE_PATH}. See "
        "https://github.com/alex-free/edcre for the tool."
    )


class CtrPatchExtension(APPatchExtension):
    """Patch extension handlers registered for the CTR apworld."""

    game: ClassVar[str] = "Crash Team Racing"

    @staticmethod
    def regenerate_ecc(caller: APProcedurePatch, rom: bytes) -> bytes:
        """
        Regenerate EDC+ECC for all CD-ROM sectors starting at sector 16
        (LBA 166, ISO9660 system volume descriptor). Sectors 0-15 are
        reserved PSX boot area and must not be touched; their EDC is
        canonically zero on licensed PSX discs.

        Writes the input bytes to a temporary file, shells out to
        EDCRE with `-s 16`, reads the modified bytes back. See module
        docstring for the TODO on replacing this with pure Python.
        """
        edcre_path = _locate_edcre()
        with tempfile.TemporaryDirectory(prefix="ctr_ecc_") as tmpdir:
            tmp_bin = os.path.join(tmpdir, "ctr.bin")
            with open(tmp_bin, "wb") as f:
                f.write(rom)
            result = subprocess.run(
                [edcre_path, "-s", "16", tmp_bin],
                capture_output=True,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"EDCRE failed with exit code {result.returncode}. "
                    f"stderr: {result.stderr.decode('utf-8', errors='replace')[:500]}"
                )
            with open(tmp_bin, "rb") as f:
                return f.read()
