#!/usr/bin/env python3
"""Build CorkDriverChecker.exe the same way as WeeklyCircularProcessor.exe."""

import shutil
import subprocess
import sys
from pathlib import Path


def install_pyinstaller():
    try:
        import PyInstaller  # noqa: F401
        print("PyInstaller is already installed")
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])


def build_executable() -> bool:
    print("Building CorkDriverChecker.exe...")
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--console",
        "--name=CorkDriverChecker",
        "--collect-all",
        "pymupdf",
        "--hidden-import",
        "fitz",
        "--hidden-import",
        "docx",
        "--hidden-import",
        "PyPDF2",
        "cork_driver_checker.py",
    ]
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as exc:
        print(f"Error building executable: {exc}")
        return False

    dist_exe = Path("dist") / "CorkDriverChecker.exe"
    if not dist_exe.exists():
        print("Build finished but dist/CorkDriverChecker.exe was not found.")
        return False

    local_exe = Path("CorkDriverChecker.exe")
    shutil.copy2(dist_exe, local_exe)
    print()
    print("Executable created.")
    print(f"  {dist_exe.resolve()}")
    print(f"  {local_exe.resolve()}  (copy next to the week folders)")
    return True


def main():
    print("Building Cork Driver Checker Executable")
    print("=" * 50)
    install_pyinstaller()
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-q", "pymupdf", "PyPDF2", "python-docx"]
    )
    if build_executable():
        print()
        print("On the work laptop:")
        print("1. Copy CorkDriverChecker.exe into the folder that has the WEEK-ENDING folders")
        print("2. Double-click CorkDriverChecker.exe")
        print("3. Pick the week, then pick the day")
        return 0
    print()
    print("Build failed. Check the error messages above.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
