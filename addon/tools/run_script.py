"""Run build scripts inside headless Blender and prove what they touched.

Always launched on a file that is never saved back (work.blend / base.blend):

    $BLENDER_BIN -b --factory-startup <file.blend> --python-exit-code 1 \
        --python tools/run_script.py -- \
        --step <section_id> <script.py> [--step <id> <script.py> ...] \
        [--touched-dir DIR] [--check-idempotent] [--save OUT.blend] \
        [--render-section ID OUT.png | --render-model OUT.png] [--report OUT.json]

For each step: snapshot bpy.data, run the script, snapshot again, diff.
- violation: the script changed or removed a datablock its section does not own,
  or created one without the section prefix. Exit code 2.
- conflict: two steps touched the same datablock. Exit code 3.
- not idempotent (--check-idempotent): running the script a second time changed
  the result. Exit code 4.
A script error exits 1. Rendering happens after all checks, with an in-memory rig.
"""

import json
import os
import runpy
import sys
import traceback

import bpy

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
sys.path.insert(0, ROOT)

import ctx_runtime  # noqa: E402
import fingerprint as fp  # noqa: E402
import preview  # noqa: E402


def parse(argv):
    args = argv[argv.index("--") + 1:] if "--" in argv else []
    o = {"steps": [], "touched_dir": None, "idem": False, "save": None,
         "render_section": None, "render_model": None, "report": None}
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--step":
            o["steps"].append((args[i + 1], os.path.abspath(args[i + 2])))
            i += 3
            continue
        if a == "--touched-dir":
            o["touched_dir"] = os.path.abspath(args[i + 1])
        elif a == "--check-idempotent":
            o["idem"] = True
            i += 1
            continue
        elif a == "--save":
            o["save"] = os.path.abspath(args[i + 1])
        elif a == "--render-model":
            o["render_model"] = os.path.abspath(args[i + 1])
        elif a == "--report":
            o["report"] = os.path.abspath(args[i + 1])
        elif a == "--render-section":
            o["render_section"] = (args[i + 1], os.path.abspath(args[i + 2]))
            i += 3
            continue
        else:
            raise SystemExit("run_script.py: unknown argument %s" % a)
        i += 2
    return o


def run_one(section_id, script):
    ctx_runtime.set_section(section_id)
    os.environ["CTX_SECTION_ID"] = section_id
    runpy.run_path(script, run_name="__main__")
    bpy.context.view_layer.update()


def check_step(section_id, script, idem):
    prefix = ctx_runtime.sm.prefix_for(section_id)
    owned_before = fp.owned_keys(section_id)
    before = fp.snapshot()
    run_one(section_id, script)
    after = fp.snapshot()
    owned_after = fp.owned_keys(section_id)
    created, modified, removed = fp.diff(before, after)

    violations = []
    for k in modified:
        if k not in owned_before and k not in owned_after:
            violations.append({"key": k, "why": "modified a datablock the section does not own"})
    for k in removed:
        if k not in owned_before:
            violations.append({"key": k, "why": "removed a datablock the section does not own"})
    for k in created:
        name = k.split("/", 1)[1]
        if not name.startswith(prefix):
            violations.append({"key": k, "why": "created without the section prefix %s" % prefix})

    result = {
        "section_id": section_id,
        "script": script,
        "prefix": prefix,
        "created": created,
        "modified": modified,
        "removed": removed,
        "violations": violations,
    }
    if idem:
        run_one(section_id, script)
        again = fp.snapshot()
        c2, m2, r2 = fp.diff(after, again)
        result["idempotent"] = not (c2 or m2 or r2)
        if not result["idempotent"]:
            result["idempotency_diff"] = {"created": c2, "modified": m2, "removed": r2}
    return result


def main():
    o = parse(sys.argv)
    if not o["steps"]:
        raise SystemExit("run_script.py: no --step given")
    results, status = [], 0
    for sid, script in o["steps"]:
        try:
            r = check_step(sid, script, o["idem"])
        except Exception:
            tb = traceback.format_exc()
            print(tb)
            r = {"section_id": sid, "script": script, "error": tb}
            results.append(r)
            status = 1
            break
        results.append(r)
        if o["touched_dir"]:
            os.makedirs(o["touched_dir"], exist_ok=True)
            with open(os.path.join(o["touched_dir"], sid + ".json"), "w") as f:
                json.dump(r, f, indent=2)
        if r["violations"]:
            status = max(status, 2)

    conflicts = []
    if status != 1:
        seen = {}
        for r in results:
            for k in set(r["created"]) | set(r["modified"]) | set(r["removed"]):
                if k in seen and seen[k] != r["section_id"]:
                    conflicts.append({"key": k, "sections": [seen[k], r["section_id"]]})
                seen.setdefault(k, r["section_id"])
        if conflicts:
            status = max(status, 3)
        if o["idem"] and any(not r.get("idempotent", True) for r in results):
            status = max(status, 4)

    report = {"status": status, "steps": results, "conflicts": conflicts}
    if o["report"]:
        with open(o["report"], "w") as f:
            json.dump(report, f, indent=2)

    for r in results:
        if r.get("error"):
            print("CTX_ERROR %s: script raised, see traceback above" % r["section_id"])
            continue
        print("CTX_STEP %s created=%d modified=%d removed=%d violations=%d%s" % (
            r["section_id"], len(r["created"]), len(r["modified"]), len(r["removed"]), len(r["violations"]),
            "" if "idempotent" not in r else " idempotent=%s" % r["idempotent"]))
        for v in r["violations"]:
            print("CTX_VIOLATION %s %s: %s" % (r["section_id"], v["key"], v["why"]))
        if r.get("idempotency_diff"):
            print("CTX_NOT_IDEMPOTENT %s %s" % (r["section_id"], json.dumps(r["idempotency_diff"])))
    for c in conflicts:
        print("CTX_CONFLICT %s touched by %s and %s" % (c["key"], c["sections"][0], c["sections"][1]))

    if status == 0:
        if o["save"]:
            os.makedirs(os.path.dirname(o["save"]), exist_ok=True)
            bpy.ops.wm.save_as_mainfile(filepath=o["save"], copy=True)
            print("CTX_SAVED", o["save"])
        if o["render_section"]:
            print("CTX_RENDER", preview.render_section(*o["render_section"]))
        elif o["render_model"]:
            print("CTX_RENDER", preview.render_model(o["render_model"]))
    print("CTX_STATUS", status)
    sys.exit(status)


if __name__ == "__main__":
    main()
