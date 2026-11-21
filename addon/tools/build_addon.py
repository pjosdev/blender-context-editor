"""Zip the add-on (board, pipeline tools, skills) as context_editor.zip for Blender's Install from Disk.

    python3 tools/build_addon.py [out_dir]     # default: dist/ beside the add-on folder; prints the zip path

Leaves out the Claude plugin files (agents/, .claude-plugin/) and caches.
"""

import os
import sys
import zipfile

PKG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # the add-on folder
PKG = "context_editor"
SKIP_DIRS = {"__pycache__", "agents", ".claude-plugin", "dist"}
KEEP = (".py", ".md", ".json")


def build(out_dir=None):
    out_dir = os.path.abspath(out_dir) if out_dir else os.path.join(os.path.dirname(PKG_DIR), "dist")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, PKG + ".zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for here, dirs, files in os.walk(PKG_DIR):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
            for name in sorted(files):
                if name.endswith(KEEP):
                    full = os.path.join(here, name)
                    rel = os.path.relpath(full, PKG_DIR).replace(os.sep, "/")
                    z.write(full, "%s/%s" % (PKG, rel))
    return out


if __name__ == "__main__":
    print(build(sys.argv[1] if len(sys.argv) > 1 else None))
