#!/usr/bin/env python3
"""
Project one-shot setup:
- Creates a virtual environment
- Installs requirements
- Registers a Jupyter kernel named 'wind_processor' by default
"""

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd, env=None, check=True):
    print(">", " ".join(str(c) for c in cmd))
    return subprocess.run(cmd, env=env, check=check)


def venv_python(venv_dir: Path) -> Path:
    if platform.system() == "Windows":
        return venv_dir / "Scripts" / "python.exe"
    else:
        return venv_dir / "bin" / "python"


def slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-").lower()
    return s or "env"


def main():
    parser = argparse.ArgumentParser(description="Create venv and Jupyter kernel for this repo.")
    parser.add_argument("--venv", default=".venv", help="Virtualenv directory (default: .venv)")
    parser.add_argument("--requirements", default="requirements.txt", help="Requirements file path")
    parser.add_argument("--name", default=None, help="Kernel name (default: wind_processor)")
    parser.add_argument("--display-name", default=None, help="Kernel display name (default: wind_processor)")
    parser.add_argument("--recreate", action="store_true", help="Delete and re-create the venv if it exists")
    args = parser.parse_args()

    repo_dir = Path.cwd()
    venv_dir = Path(args.venv)
    req_file = Path(args.requirements)

    # Defaults per your request
    kernel_name = args.name or "wind_processor"
    kernel_display = args.display_name or "wind_processor"

    # 1) (Re)create venv
    if venv_dir.exists() and args.recreate:
        print(f"Removing existing venv: {venv_dir}")
        shutil.rmtree(venv_dir)

    if not venv_dir.exists():
        print(f"Creating virtual environment at: {venv_dir}")
        run([sys.executable, "-m", "venv", str(venv_dir)])
    else:
        print(f"Using existing virtual environment at: {venv_dir}")

    py = venv_python(venv_dir)
    if not py.exists():
        print(f"ERROR: Could not find interpreter inside venv at {py}")
        sys.exit(1)

    # 2) Upgrade pip/setuptools/wheel
    run([str(py), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])

    # 3) Install requirements (if present)
    if req_file.exists():
        print(f"Installing requirements from {req_file} …")
        run([str(py), "-m", "pip", "install", "-r", str(req_file)])
    else:
        print(f"WARNING: {req_file} not found. Skipping requirements installation.")

    # 4) Ensure Jupyter & ipykernel are present
    run([str(py), "-m", "pip", "install", "ipykernel", "jupyterlab", "notebook"])

    # 5) Register the kernel (user-level)
    run([
        str(py), "-m", "ipykernel", "install",
        "--user",
        "--name", kernel_name,
        "--display-name", kernel_display
    ])

    # 6) (Optional) Enable widgets for classic notebook (harmless if it fails)
    try:
        run([str(py), "-m", "jupyter", "nbextension", "enable", "--py", "widgetsnbextension", "--sys-prefix"], check=False)
    except Exception:
        pass

    print("\n✅ Setup complete.")
    print(f"- Virtualenv: {venv_dir}")
    print(f"- Kernel:     {kernel_display}  (name: {kernel_name})\n")
    print("Next steps:")
    if platform.system() == "Windows":
        print(rf"  {venv_dir}\Scripts\jupyter-lab.exe")
    else:
        print(f"  {venv_dir}/bin/jupyter lab")
    print("…or run your existing Jupyter and select the 'wind_processor' kernel from the Kernel menu.")


if __name__ == "__main__":
    main()
