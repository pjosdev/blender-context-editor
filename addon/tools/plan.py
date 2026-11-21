"""Write plan.json (+ a plan.md skeleton the lead fills in) for a run folder.

    python3 tools/plan.py runs/<run> [--only <id> ...]

Tasks: every section with status "ready", in waves so a child section runs
after its parent. "locked" and "draft" sections are skipped.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_folder as rf  # noqa: E402


def main(argv):
    if not argv:
        sys.exit(__doc__)
    run_dir = os.path.abspath(argv[0])
    only = argv[argv.index("--only") + 1:] if "--only" in argv else None
    ctx = rf.load_context(run_dir)
    by = rf.sections_by_id(ctx)
    ids = [s["id"] for s in rf.build_order(ctx["sections"]) if s["status"] == "ready"]
    if only:
        ids = [i for i in ids if i in only or any(i.startswith(o) for o in only)]
    w = rf.waves(ctx, ids)
    plan = {"run_dir": run_dir, "waves": w, "tasks": []}
    for i in ids:
        s = by[i]
        plan["tasks"].append({
            "id": i,
            "title": s["title"],
            "collection_path": s["collection_path"],
            "order": s["order"],
            "parent_id": s.get("parent_id"),
            "script": os.path.relpath(rf.script_path(run_dir, s), run_dir),
            "work_blend": "work/%s/work.blend" % i,
        })
    with open(os.path.join(run_dir, "plan.json"), "w") as f:
        json.dump(plan, f, indent=2)

    md = os.path.join(run_dir, "plan.md")
    if not os.path.isfile(md):
        lines = ["# Plan", "", "Run: `%s`" % run_dir, ""]
        for n, wave in enumerate(w, 1):
            lines.append("## Wave %d" % n)
            for i in wave:
                s = by[i]
                dep = " (after parent %s)" % by[s["parent_id"]]["title"] if s.get("parent_id") in by else ""
                lines.append("- **%s** `%s` · `%s`%s" % (s["title"], s["collection_path"], i[:6], dep))
                lines.append("  - Task: ")
            lines.append("")
        with open(md, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    print(json.dumps({"waves": [[by[i]["title"] for i in wv] for wv in w]}, indent=2))


if __name__ == "__main__":
    main(sys.argv[1:])
