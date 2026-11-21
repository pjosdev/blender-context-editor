"""Export a .blend's context board without opening the UI (same code as the Export button).

    $BLENDER_BIN -b --factory-startup file.blend --python tools/export_headless.py

$CTX_RUNS_DIR overrides the scene's runs folder.
Prints CTX_RUN <run_dir> and waits for the block-out and sketch previews to finish.
The .blend itself is not saved.
"""

import os
import sys

import bpy

import importlib  # noqa: E402

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # the add-on folder
sys.path.insert(0, os.path.dirname(PKG))
addon = importlib.import_module(os.path.basename(PKG))
addon.register()
export = importlib.import_module(addon.__name__ + ".export")

if os.environ.get("CTX_RUNS_DIR"):
    bpy.context.scene.ctx_runs_dir = os.environ["CTX_RUNS_DIR"]
run_dir, ctx, proc = export.export_run(bpy.context.scene)
if proc is not None:
    proc.wait()
    sm = importlib.import_module(addon.__name__ + ".scene_model")
    wanted = [s["blockout_preview"] for s in ctx["sections"]] + [k["image"] for _, k in sm.iter_sketches(ctx)]
    missing = [p for p in wanted if not os.path.isfile(os.path.join(run_dir, p))]
    if missing:
        print("CTX_PREVIEW_MISSING", missing)
        sys.exit(1)
print("CTX_RUN", run_dir)
