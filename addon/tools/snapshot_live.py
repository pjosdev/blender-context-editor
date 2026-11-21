"""Make a run folder from the open Blender session (via the Blender MCP server).

Run inside Blender with execute_blender_code:

    import runpy
    result = runpy.run_path("<addon>/tools/snapshot_live.py", run_name="ctx_snapshot")["snapshot"]("<folder>")

<addon> is the installed Context Editor add-on's folder; <folder> is the session's working folder.
Uses the add-on's export (the same code as the Export button) and writes <folder>/runs/<run>/:
context.json, base.blend (a copy; the open file is not saved), refs/, sketches/, and starts the
preview renders in a background Blender.
Returns {"run_dir", "addon_dir", "python_bin", "blender_bin", "source_blend", "sections"} or {"error": ...}.
Then wait for the previews with `<python_bin> <addon>/tools/wait_previews.py <run_dir>`.
"""

import ast
import os
import sys

import addon_utils
import bpy

ADDON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _disk_version():
    with open(os.path.join(ADDON_DIR, "__init__.py"), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "bl_info":
            return tuple(ast.literal_eval(node.value)["version"])
    return None


def snapshot(folder):
    if not addon_utils.check("context_editor")[1]:
        return {"error": "The Context Editor add-on is not enabled in this Blender. Enable it in "
                         "Edit > Preferences > Add-ons, then snapshot again."}
    loaded = sys.modules.get("context_editor")  # what's running, not what's on disk
    if loaded is None or os.path.normcase(os.path.dirname(os.path.abspath(loaded.__file__))) != os.path.normcase(ADDON_DIR):
        return {"error": "Run this file from the installed add-on's folder (%s), not %s."
                         % (os.path.dirname(loaded.__file__) if loaded else "?", ADDON_DIR)}
    running, on_disk = tuple(loaded.bl_info.get("version", ())), _disk_version()
    if running != on_disk:
        return {"error": "Blender is running Context Editor %s but %s is installed. Save your work and "
                         "restart Blender." % (running, on_disk)}
    if not bpy.data.filepath:
        return {"error": "The open file has never been saved. Save it, then snapshot again."}
    from context_editor import export

    try:
        run_dir, ctx, _proc = export.export_run(bpy.context.scene, runs_dir=os.path.join(os.path.abspath(folder), "runs"))
    except Exception as e:  # noqa: BLE001 - reported verbatim to the lead
        return {"error": str(e)}
    return {
        "run_dir": run_dir,
        "addon_dir": ADDON_DIR,
        "python_bin": sys.executable,
        "blender_bin": bpy.app.binary_path,
        "source_blend": bpy.data.filepath,
        "unsaved_changes": bpy.data.is_dirty,
        "sections": [{"title": s["title"], "status": s["status"]} for s in ctx["sections"]],
    }
