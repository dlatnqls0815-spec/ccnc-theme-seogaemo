#!/usr/bin/env python3
"""Download the two upstream inputs into upstream/ and check them.

This repository does not contain the ccNC theme itself (its author keeps all rights).
This script fetches it from the author's own GitHub release, and the HMG-Seogaemo
source that the adapter is compiled against.

  upstream/ccnc-theme-0.1.31/   ccnc-theme-for-5w-0.1.31.zip (blackr), SHA-256 checked
  upstream/hmg-seogaemo/        HMG-Seogaemo v0.1.54 source (AGPL-3.0), commit checked
"""
import hashlib
import io
from pathlib import Path
import shutil
import sys
import tarfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
UP = ROOT / "upstream"
THEME_URL = "https://github.com/b-lack-kr/ccnc-theme-for-5w/releases/download/v0.1.31-beta/ccnc-theme-for-5w-0.1.31.zip"
THEME_SHA256 = "015d7efad7e7d7bedf2fb669ca7cffdf60a68875fdcbf2eb300f039c827b72a0"
SG_COMMIT = "2f0ad48c228932bc5f5639ea59eac9a1e40b260a"  # tag v0.1.54
SG_URL = f"https://codeload.github.com/seogaemo/hmg-seogaemo/tar.gz/{SG_COMMIT}"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "ccnc-theme-seogaemo-build"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def main():
    UP.mkdir(exist_ok=True)
    theme_dir = UP / "ccnc-theme-0.1.31"
    if not (theme_dir / "hooks.jar").is_file():
        data = get(THEME_URL)
        digest = hashlib.sha256(data).hexdigest()
        if digest != THEME_SHA256:
            sys.exit(f"theme zip SHA-256 mismatch: {digest}")
        theme_dir.mkdir(exist_ok=True)
        zipfile.ZipFile(io.BytesIO(data)).extractall(theme_dir)
        print("theme 0.1.31: OK")
    else:
        print("theme 0.1.31: already present")

    sg_dir = UP / "hmg-seogaemo"
    if not (sg_dir / "VERSION").is_file():
        data = get(SG_URL)
        tmp = UP / "hmg-seogaemo.tmp"
        shutil.rmtree(tmp, ignore_errors=True)
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            prefix = f"hmg-seogaemo-{SG_COMMIT}/"
            for m in tar.getmembers():
                if not m.name.startswith(prefix) or ".." in Path(m.name).parts or not (m.isfile() or m.isdir()):
                    continue
                m.name = m.name[len(prefix):]
                if m.name:
                    tar.extract(m, tmp)
        version = (tmp / "VERSION").read_text().strip()
        if version != "0.1.54":
            shutil.rmtree(tmp, ignore_errors=True)
            sys.exit(f"unexpected HMG-Seogaemo VERSION {version}")
        tmp.rename(sg_dir)
        print("HMG-Seogaemo 0.1.54: OK")
    else:
        print("HMG-Seogaemo: already present")


if __name__ == "__main__":
    main()
