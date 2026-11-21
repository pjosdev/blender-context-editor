"""Make each section's isolated working copy.

    python3 tools/make_copies.py runs/<run> <section_id> [<section_id> ...]

work/<id>/work.blend = base.blend, plus the build scripts of the section's
ancestors applied in order (accepted script if decided, else the latest one),
so a child section builds on its parent's result. Also creates the section's
previews/ and reports/ folders. Never touches base.blend or the original file.
"""

import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blender_bin as bb  # noqa: E402
import run_folder as rf  # noqa: E402


def make_copy(run_dir, ctx, section_id):
    base = os.path.join(run_dir, "base.blend")
    work_dir = os.path.join(run_dir, "work", section_id)
    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(os.path.join(run_dir, "previews", section_id), exist_ok=True)
    os.makedirs(os.path.join(run_dir, "reports"), exist_ok=True)
    os.makedirs(os.path.join(run_dir, "scripts"), exist_ok=True)
    work = os.path.join(work_dir, "work.blend")

    steps = []
    for anc in rf.ancestors(ctx, section_id):
        script = rf.find_script(run_dir, anc["id"])
        if script:
            steps += ["--step", anc["id"], script]
    if not steps:
        shutil.copy2(base, work)
        return work, []
    code, out = bb.run_blender(base, os.path.join(bb.TOOLS, "run_script.py"),
                               steps + ["--save", work], os.path.join(work_dir, "make_copy.log"),
                               run_dir=run_dir)
    if code != 0:
        sys.exit("make_copies: applying parent scripts for %s failed (exit %d), see %s"
                 % (section_id, code, os.path.join(work_dir, "make_copy.log")))
    return work, steps[2::3]


def main(argv):
    if len(argv) < 2:
        sys.exit(__doc__)
    run_dir = os.path.abspath(argv[0])
    ctx = rf.load_context(run_dir)
    by = rf.sections_by_id(ctx)
    for arg in argv[1:]:
        sid = next((i for i in by if i == arg or i.startswith(arg)), None)
        if sid is None:
            sys.exit("make_copies: no section %s" % arg)
        work, parents = make_copy(run_dir, ctx, sid)
        print("%s  %s%s" % (by[sid]["title"], os.path.relpath(work, run_dir),
                            "  (+ parent scripts: %s)" % ", ".join(os.path.basename(p) for p in parents) if parents else ""))


if __name__ == "__main__":
    main(sys.argv[1:])
