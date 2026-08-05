from __future__ import annotations

# PyInstaller entry point for the reader. PyInstaller needs a plain script (it can't target
# `python -m src.workflows.run_reader`), so this thin wrapper just calls the same main().
# Build: see packaging/build_exe.py
from src.workflows.run_reader import main

if __name__ == "__main__":
    main()
