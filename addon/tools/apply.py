"""Apply accepted scripts to the artist's original .blend, after backing it up.

    python3 tools/apply.py runs/<run> [--target path/to/file.blend]

1. Copies the target to <name>.ctx-backup-<timestamp>.blend next to it.
2. Opens the target headless, runs the accepted scripts in build order with the
   same ownership checks as the merge, and saves over the target only if every
   check passes. On any failure the target is left untouched.

Close the file in Blender first (or use tools/apply_live.py through the Blender
MCP connection to apply into the open session). Section ids are looked up by
ctx_section_id, so the artist's edits since export are kept; the scripts call
sec.clean() first, so applying twice gives the same result.
"""

import datetime
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blender_bin as bb  # noqa: E402
import run_folder as rf  # noqa: E402


def backup(path):
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    root, ext = os.path.splitext(path)
    dst = "%s.ctx-backup-%s%s" % (root, stamp, ext)
    shutil.copy2(path, dst)
    return dst


def main(argv):
    if not argv:
        sys.exit(__doc__)
    run_dir = os.path.abspath(argv[0])
    ctx = rf.load_context(run_dir)
    target = os.path.abspath(argv[argv.index("--target") + 1]) if "--target" in argv else ctx["source_blend"]
    if not os.path.isfile(target):
        sys.exit("apply: target %s does not exist" % target)
    dec = rf.load_decisions(run_dir)
    steps = []
    for s in rf.build_order(ctx["sections"]):
        script = rf.find_script(run_dir, s["id"])
        if script and dec.get(s["id"], {}).get("decision") == "accept":
            steps += ["--step", s["id"], script]
    if not steps:
        sys.exit("apply: no accepted scripts")
    saved = backup(target)
    print("Backup: %s" % saved)
    tmp = os.path.join(run_dir, "apply_result.blend")
    code, out = bb.run_blender(target, os.path.join(bb.TOOLS, "run_script.py"),
                               steps + ["--save", tmp, "--report", os.path.join(run_dir, "apply_report.json")],
                               os.path.join(run_dir, "apply.log"), run_dir=run_dir)
    if code != 0 or not os.path.isfile(tmp):
        sys.exit("apply: checks failed (exit %d); %s is unchanged. See apply.log / apply_report.json." % (code, target))
    shutil.copy2(tmp, target)
    os.remove(tmp)
    print("Applied %d scripts to %s" % (len(steps) // 3, target))


if __name__ == "__main__":
    main(sys.argv[1:])
