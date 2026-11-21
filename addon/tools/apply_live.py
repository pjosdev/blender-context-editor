"""Apply accepted scripts into the open Blender session (via the Blender MCP server).

Run inside Blender with execute_blender_code:

    import runpy
    runpy.run_path("<addon>/tools/apply_live.py", run_name="ctx_apply")["apply"]("<folder>/runs/<run>")

1. Saves a backup copy of the open file (<name>.ctx-backup-<timestamp>.blend);
   refuses to run if the file was never saved.
2. Runs accepted scripts in build order with the ownership checks, one undo step each.
3. Stops at the first violation, error or conflict and reports it. The backup and
   Ctrl+Z are the way back. The open file is not saved; the artist saves.
"""

import datetime
import json
import os
import sys

import bpy

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.dirname(TOOLS))

import run_folder as rf  # noqa: E402
import run_script  # noqa: E402


def apply(run_dir):
    run_dir = os.path.abspath(run_dir)
    if not bpy.data.filepath:
        return {"ok": False, "error": "Save the open file first, so there is something to back up."}
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    root, ext = os.path.splitext(bpy.data.filepath)
    backup = "%s.ctx-backup-%s%s" % (root, stamp, ext)
    bpy.ops.wm.save_as_mainfile(filepath=backup, copy=True)

    ctx = rf.load_context(run_dir)
    dec = rf.load_decisions(run_dir)
    done, seen = [], {}
    for s in rf.build_order(ctx["sections"]):
        script = rf.find_script(run_dir, s["id"])
        if not script or dec.get(s["id"], {}).get("decision") != "accept":
            continue
        r = run_script.check_step(s["id"], script, idem=False)
        bpy.ops.ed.undo_push(message="Context: apply %s" % s["title"])
        problems = [v["key"] + ": " + v["why"] for v in r["violations"]]
        for k in set(r["created"]) | set(r["modified"]) | set(r["removed"]):
            if k in seen:
                problems.append("%s also touched by %s" % (k, seen[k]))
            seen.setdefault(k, s["title"])
        done.append(s["title"])
        if problems:
            return {"ok": False, "backup": backup, "applied": done, "stopped_at": s["title"], "problems": problems}
    return {"ok": True, "backup": backup, "applied": done}


if __name__ == "__main__":
    print(json.dumps(apply(sys.argv[sys.argv.index("--") + 1]), indent=2))
