from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

# Build a standalone sensor-reader.exe (no Python install needed on the target PC) so the reader
# can be deployed to shop-floor Windows PCs by copying 2 files: the exe + a .env beside it.
# Run: python packaging/build_exe.py

_ROOT = Path(__file__).resolve().parent.parent
_ENTRY = _ROOT / "packaging" / "reader_entry.py"
_DIST = _ROOT / "dist-exe"

# Imported indirectly (via src.storage / src.sensor.transport), so PyInstaller's static analysis
# can miss them -- declare them explicitly.
_HIDDEN_IMPORTS = ("oracledb", "serial")

# Packages PyInstaller must pull in WHOLE (submodules + data + native binaries), not just the
# top-level module. `cryptography` is imported lazily by oracledb's thin mode and ships compiled
# Rust binaries, so a plain hidden-import isn't enough -- without this the exe builds fine but
# fails at runtime with "DPY-3016 ... cryptography package cannot be imported".
_COLLECT_ALL = ("cryptography", "oracledb")


# Run PyInstaller with this project's layout, returning its exit code.
def build() -> int:
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--name",
        "sensor-reader",
        "--paths",
        str(_ROOT),
        "--distpath",
        str(_DIST),
        "--workpath",
        str(_ROOT / "build-exe"),
        "--specpath",
        str(_ROOT / "packaging"),
        "--noconfirm",
        str(_ENTRY),
    ]
    for name in _HIDDEN_IMPORTS:
        command.extend(["--hidden-import", name])
    for name in _COLLECT_ALL:
        command.extend(["--collect-all", name])

    return subprocess.call(command, cwd=_ROOT)


# Build, then drop a .env template next to the exe so the deploy step is "copy this folder".
def main() -> None:
    if shutil.which("python") is None and not sys.executable:
        raise RuntimeError("Python interpreter not found")

    exit_code = build()
    if exit_code != 0:
        sys.exit(exit_code)

    template = _ROOT / ".env.example"
    if template.exists():
        shutil.copy(template, _DIST / ".env.example")

    print(f"\nビルド完了: {_DIST / 'sensor-reader.exe'}")
    print("配布手順: exe と .env（.env.example をコピーして編集）を同じフォルダに置いて実行してください。")


if __name__ == "__main__":
    main()
