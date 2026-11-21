"""Append the model that builds a run to its folder name, before any worker starts.

    python3 tools/name_run.py runs/2026-11-20_1318_bikething opus-xhigh
    -> runs/2026-11-20_1318_bikething_opus-xhigh   (prints the new path)

Rewrites the run path in plan.json and plan.md. Refuses once work/ or scripts/ exist, because
working copies and worker reports would still point at the old path. Stdlib only.
"""

import json
import os
import re
import sys


def main(argv):
    if len(argv) != 2:
        sys.exit(__doc__)
    run_dir = os.path.abspath(argv[0].rstrip("/\\"))
    label = re.sub(r"[^a-z0-9.-]+", "-", argv[1].lower()).strip("-")
    if not os.path.isfile(os.path.join(run_dir, "context.json")):
        sys.exit("name_run: %s is not a run folder" % run_dir)
    if not label:
        sys.exit("name_run: empty label")
    base = os.path.basename(run_dir)
    if base.endswith("_" + label):
        print(run_dir)
        return
    for sub in ("work", "scripts"):
        if os.path.isdir(os.path.join(run_dir, sub)) and os.listdir(os.path.join(run_dir, sub)):
            sys.exit("name_run: %s already has %s/; label runs before the first worker" % (base, sub))
    new_dir = os.path.join(os.path.dirname(run_dir), "%s_%s" % (base, label))
    if os.path.exists(new_dir):
        sys.exit("name_run: %s already exists" % new_dir)
    os.rename(run_dir, new_dir)
    pj = os.path.join(new_dir, "plan.json")
    if os.path.isfile(pj):
        with open(pj) as f:
            plan = json.load(f)
        plan["run_dir"] = new_dir
        with open(pj, "w") as f:
            json.dump(plan, f, indent=2)
    pm = os.path.join(new_dir, "plan.md")
    if os.path.isfile(pm):
        with open(pm) as f:
            text = f.read()
        with open(pm, "w") as f:
            f.write(text.replace(run_dir, new_dir))
    print(new_dir)


if __name__ == "__main__":
    main(sys.argv[1:])
