"""Run one section's build script on its working copy, checked and rendered. Stdlib only.

The worker's loop command, the same on macOS, Linux and Windows:

    python3 tools/run_section.py runs/<run> <id> <iteration> [--with <neighbour_id> ...]

- Uses the Blender recorded in context.json, -b --factory-startup, on work/<id>/work.blend
  (never saved), through tools/run_script.py with --check-idempotent.
- Writes touched/<id>.json and, if the status is 0, previews/<id>/iter_<iteration>.png.
- --with runs those sections' current scripts first, to check fit against a neighbour. Touched files
  then go to touched/_scratch/ and no preview is written, so the section's real record stays clean.
- Prints only the CTX_ lines, errors and tracebacks. Exit code = run_script.py's status:
  0 clean, 1 script error, 2 violation, 3 conflict, 4 not idempotent.
"""

import os
import re
import subprocess
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import blender_bin as bb  # noqa: E402
import run_folder as rf  # noqa: E402

KEEP = re.compile(r"CTX_|Error|Traceback|line \d+")


def full_id(by, sid):
    full = next((i for i in by if i == sid or i.startswith(sid)), None)
    if full is None:
        sys.exit("run_section: no section %s" % sid)
    return full


def main(argv):
    if len(argv) < 3:
        sys.exit(__doc__)
    run_dir = os.path.abspath(argv[0])
    ctx = rf.load_context(run_dir)
    by = rf.sections_by_id(ctx)
    sid = full_id(by, argv[1])
    it = int(argv[2])
    others = [full_id(by, o) for o in argv[argv.index("--with") + 1:]] if "--with" in argv else []

    work = os.path.join(run_dir, "work", sid, "work.blend")
    if not os.path.isfile(work):
        sys.exit("run_section: no working copy %s (run make_copies.py first)" % work)
    steps = []
    for o in others:
        script = rf.find_script(run_dir, o)
        if not script:
            sys.exit("run_section: %s has no script yet" % by[o]["title"])
        steps += ["--step", o, script]
    steps += ["--step", sid, rf.script_path(run_dir, by[sid])]

    args = steps + ["--check-idempotent"]
    if others:
        args += ["--touched-dir", os.path.join(run_dir, "touched", "_scratch")]
    else:
        out = os.path.join(run_dir, "previews", sid, "iter_%d.png" % it)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        args += ["--touched-dir", os.path.join(run_dir, "touched"), "--render-section", sid, out]

    cmd = [bb.blender_bin(run_dir), "-b", "--factory-startup", work, "--python-exit-code", "1",
           "--python", os.path.join(TOOLS, "run_script.py"), "--"] + args
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       text=True, encoding="utf-8", errors="replace")
    for line in p.stdout.splitlines():
        if KEEP.search(line):
            print(line)
    return p.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
