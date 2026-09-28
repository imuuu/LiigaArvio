"""Auto-update on startup: fast-forward the local git checkout from its remote.

Standard library only. Never blocks startup: every failure (no git, no network,
local edits, diverged history) is reported and the app starts with the current code.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

SKIP_ENV = "LIIGAARVIO_NO_UPDATE"


def _git(root: Path, *args: str, timeout: float = 20) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def update(root: Path) -> bool:
    """Pull new commits if the checkout is behind its upstream. Returns True if code changed."""
    if os.environ.get(SKIP_ENV):
        return False
    if not (root / ".git").exists():
        print("Automaattipäivitys ohitettu: kansio ei ole git-klooni.")
        return False
    if shutil.which("git") is None:
        print("Automaattipäivitys ohitettu: git-ohjelmaa ei löydy.")
        return False
    try:
        if _git(root, "rev-parse", "--abbrev-ref", "@{u}").returncode != 0:
            print("Automaattipäivitys ohitettu: haaralla ei ole etärepoa.")
            return False
        print("Tarkistetaan päivitykset...")
        fetch = _git(root, "fetch", "--quiet")
        if fetch.returncode != 0:
            print("Päivitysten haku epäonnistui (ei verkkoa?). Käynnistetään nykyinen versio.")
            return False
        before = _git(root, "rev-parse", "HEAD").stdout.strip()
        behind = _git(root, "rev-list", "--count", "HEAD..@{u}").stdout.strip()
        if behind in ("", "0"):
            print("Sovellus on ajan tasalla.")
            return False
        pull = _git(root, "merge", "--ff-only", "--quiet", "@{u}", timeout=60)
        if pull.returncode != 0:
            print("Päivitystä ei voitu asentaa (paikallisia muutoksia?). Käynnistetään nykyinen versio.")
            print(pull.stderr.strip())
            return False
        after = _git(root, "rev-parse", "HEAD").stdout.strip()
        if after == before:
            return False
        log = _git(root, "log", "--oneline", f"{before}..{after}").stdout.strip()
        print(f"Päivitetty {behind} uudella muutoksella:")
        print(log)
        return True
    except (OSError, subprocess.TimeoutExpired) as exc:
        print("Automaattipäivitys epäonnistui:", exc)
        return False
