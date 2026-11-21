"""Run-folder helpers shared by the stdlib CLIs. Stdlib only."""

import glob
import json
import os


def load_context(run_dir):
    with open(os.path.join(run_dir, "context.json")) as f:
        return json.load(f)


def sections_by_id(ctx):
    return {s["id"]: s for s in ctx["sections"]}


def script_path(run_dir, section):
    return os.path.join(run_dir, "scripts", "%02d_%s.py" % (section["order"], section["id"]))


def find_script(run_dir, section_id):
    hits = sorted(glob.glob(os.path.join(run_dir, "scripts", "*_%s.py" % section_id)))
    return hits[-1] if hits else None


def load_decisions(run_dir):
    p = os.path.join(run_dir, "decisions.json")
    if not os.path.isfile(p):
        return {}
    with open(p) as f:
        return json.load(f)


def save_decisions(run_dir, d):
    with open(os.path.join(run_dir, "decisions.json"), "w") as f:
        json.dump(d, f, indent=2)


def ancestors(ctx, section_id):
    """Parent chain, root first."""
    by = sections_by_id(ctx)
    chain = []
    p = by[section_id].get("parent_id")
    while p and p in by:
        chain.append(by[p])
        p = by[p].get("parent_id")
    return list(reversed(chain))


def build_order(sections):
    """Parents before children, then by order."""
    return sorted(sections, key=lambda s: (s.get("depth", 0), s["order"], s["collection_path"]))


def waves(ctx, section_ids):
    """Group sections so every section runs after its parent's wave."""
    by = sections_by_id(ctx)
    todo = [by[i] for i in section_ids]
    out = []
    done = set()
    pending = {s["id"] for s in todo}
    while todo:
        wave = [s for s in todo if not (s.get("parent_id") in pending and s.get("parent_id") not in done)]
        if not wave:
            wave = todo[:]
        wave = build_order(wave)
        out.append([s["id"] for s in wave])
        done.update(s["id"] for s in wave)
        todo = [s for s in todo if s["id"] not in done]
    return out
