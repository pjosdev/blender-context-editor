"""Merge accepted section scripts into build.blend.

    python3 tools/merge.py runs/<run>            # accepted sections -> build.blend
    python3 tools/merge.py runs/<run> --all      # every section with a script -> build_provisional.blend
                                               # (seam check before review)

Runs the scripts in order (parents first, then `order`) on a fresh base.blend,
with the same datablock diff as the workers. Stops with a clear message if two
scripts touched the same datablock, or a script touched something it doesn't own.
Renders previews/build.png (or build_provisional.png).
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blender_bin as bb  # noqa: E402
import run_folder as rf  # noqa: E402


def main(argv):
    if not argv:
        sys.exit(__doc__)
    run_dir = os.path.abspath(argv[0])
    provisional = "--all" in argv
    ctx = rf.load_context(run_dir)
    decisions = rf.load_decisions(run_dir)

    chosen = []
    for s in rf.build_order(ctx["sections"]):
        script = rf.find_script(run_dir, s["id"])
        if script is None:
            continue
        if provisional or decisions.get(s["id"], {}).get("decision") == "accept":
            chosen.append((s, script))
    if not chosen:
        sys.exit("merge: nothing to merge (no %s scripts)" % ("" if provisional else "accepted"))

    name = "build_provisional" if provisional else "build"
    steps = []
    for s, script in chosen:
        steps += ["--step", s["id"], script]
    report = os.path.join(run_dir, name + "_report.json")
    args = steps + [
        "--save", os.path.join(run_dir, name + ".blend"),
        "--render-model", os.path.join(run_dir, "previews", name + ".png"),
        "--report", report,
        "--touched-dir", os.path.join(run_dir, "touched", name),
    ]
    code, out = bb.run_blender(os.path.join(run_dir, "base.blend"), os.path.join(bb.TOOLS, "run_script.py"),
                               args, os.path.join(run_dir, name + ".log"), run_dir=run_dir)
    titles = {s["id"]: s["title"] for s in ctx["sections"]}
    print("Merged in order: " + " -> ".join(titles[s["id"]] for s, _ in chosen))
    if not os.path.isfile(report):
        print(out[-3000:])
        sys.exit("merge: Blender failed before writing a report (exit %d), see %s.log" % (code, name))
    with open(report) as f:
        rep = json.load(f)
    for st in rep["steps"]:
        if st.get("error"):
            print("ERROR in %s (%s):\n%s" % (titles.get(st["section_id"]), st["script"], st["error"]))
        for v in st.get("violations", []):
            print("VIOLATION in %s: %s %s" % (titles.get(st["section_id"]), v["key"], v["why"]))
    for c in rep["conflicts"]:
        print("CONFLICT: %s was touched by both %s and %s. Not guessing; fix one script or the "
              "ownership and merge again." % (c["key"], titles.get(c["sections"][0]), titles.get(c["sections"][1])))
    if code != 0:
        sys.exit("merge: stopped (exit %d). Nothing was saved." % code)
    print("Saved %s.blend and previews/%s.png" % (name, name))


if __name__ == "__main__":
    main(sys.argv[1:])
