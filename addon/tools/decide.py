"""Record the artist's keep / redo calls for a run. Stdlib only.

    python3 tools/decide.py runs/<run>                                  # list sections and their calls
    python3 tools/decide.py runs/<run> <id> keep
    python3 tools/decide.py runs/<run> <id> redo --note "seats too clean, add wear"

The artist looks at build_provisional.blend in Blender and says keep or redo per section; the lead
records it here. decisions.json stores "accept" (keep) or "reject" (redo); merge and apply use only
accepted sections. A redo appends the note to feedback/<id>.md, which the next rebuild of that
section reads. <id> may be the first 6 characters of the section id.
"""

import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_folder as rf  # noqa: E402

WORDS = {"keep": "accept", "accept": "accept", "redo": "reject", "reject": "reject"}


def decide(run_dir, sid, word, note):
    by = rf.sections_by_id(rf.load_context(run_dir))
    full = next((i for i in by if i == sid or i.startswith(sid)), None)
    if full is None:
        sys.exit("decide: no section %s" % sid)
    if word not in WORDS:
        sys.exit("decide: say keep or redo")
    d = rf.load_decisions(run_dir)
    d[full] = {"decision": WORDS[word], "note": note, "at": datetime.datetime.now().isoformat(timespec="seconds")}
    rf.save_decisions(run_dir, d)
    if d[full]["decision"] == "reject":
        os.makedirs(os.path.join(run_dir, "feedback"), exist_ok=True)
        with open(os.path.join(run_dir, "feedback", full + ".md"), "a", encoding="utf-8") as f:
            f.write("## Redo %s\n\n%s\n\n" % (d[full]["at"], note or "(no note)"))
    print("%s: %s" % (by[full]["title"], "keep" if d[full]["decision"] == "accept" else "redo"))


def show(run_dir):
    ctx = rf.load_context(run_dir)
    d = rf.load_decisions(run_dir)
    for s in rf.build_order(ctx["sections"]):
        call = {"accept": "keep", "reject": "redo"}.get(d.get(s["id"], {}).get("decision"), "undecided")
        built = "built" if rf.find_script(run_dir, s["id"]) else "not built"
        print("%s  %-28s %-10s %s" % (s["id"][:6], s["title"], built, call))


def main(argv):
    if not argv:
        sys.exit(__doc__)
    run_dir = os.path.abspath(argv[0])
    if len(argv) >= 3:
        note = argv[argv.index("--note") + 1] if "--note" in argv else ""
        decide(run_dir, argv[1], argv[2], note)
    else:
        show(run_dir)


if __name__ == "__main__":
    main(sys.argv[1:])
