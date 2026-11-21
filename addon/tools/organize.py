"""Rename objects and sort them into collections, in the open Blender (via the Blender MCP server).

Run inside Blender with execute_blender_code:

    import runpy
    ns = runpy.run_path("<addon>/tools/organize.py", run_name="ctx_organize")
    result = ns["inspect"]("<folder>")                          # 1. look
    result = ns["apply"]("<folder>/organize/<ts>/organize.json", dry_run=True)   # 2. check the plan
    result = ns["apply"]("<folder>/organize/<ts>/organize.json")                 # 3. do it

<folder> is the session's working folder. inspect() writes <folder>/organize/<ts>/scene.json (every object: type, size, bounds, materials,
collections, owning section) and source.blend (a copy, for tools/organize_sheets.py).

organize.json (written by the lead):

    {"objects": [{"name": "Cube.012", "new_name": "hull_plate_left", "collection": ["Ship", "Hull"]}]}

``new_name`` and ``collection`` are each optional. ``collection`` is a path of collection names
from the scene root; missing ones are created there, existing ones must already sit at that place
(collections are never renamed or moved). A moved object leaves every other collection it was in.

The whole plan is checked first and nothing changes if anything fails. Checks: the object exists,
is local and isn't pipeline data (ctx_*, CTX_*); new names are unique, free and not ctx_/CTX_;
an object stays in the same Context Editor section; no object leaves a collection that another
object instances. Then a backup copy is saved next to the file (<name>.ctx-backup-<ts>.blend),
the changes run as one undo step, and nothing is deleted. The open file is not saved.

Headless (tests): blender -b f.blend --python organize.py -- inspect <folder> | apply <organize.json> [--save]
"""

import datetime
import json
import os
import sys

import bpy

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(TOOLS))
import scene_model as sm  # noqa: E402

LOCKED_PREFIXES = ("ctx_", "CTX_")
GEOMETRY = {"MESH", "CURVE", "SURFACE", "FONT", "META", "GREASEPENCIL", "CURVES"}


def _locked(obj):
    if obj.name.startswith(LOCKED_PREFIXES):
        return "pipeline object (ctx_/CTX_ name)"
    if obj.library or obj.override_library:
        return "linked from another file"
    return None


def _paths(parents):
    return lambda c: sm.collection_path(c, parents)


def _section_name(coll):
    return coll.name if coll is not None else None


def _instanced_collections():
    return {o.instance_collection.name for o in bpy.data.objects
            if o.instance_type == "COLLECTION" and o.instance_collection}


# ---------------------------------------------------------------- inspect

def inspect(folder):
    scene = bpy.context.scene
    parents = sm.collection_parents(scene)
    path = _paths(parents)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = os.path.join(os.path.abspath(folder), "organize", stamp)
    os.makedirs(out, exist_ok=True)

    objects, tile = [], 0
    for o in sorted(scene.objects, key=lambda o: o.name):
        bb = sm.world_bbox([o])
        info = {
            "name": o.name,
            "type": o.type,
            "data": o.data.name if o.data else None,
            "data_users": o.data.users if o.data else 0,
            "materials": [s.material.name for s in o.material_slots if s.material],
            "modifiers": [m.type for m in o.modifiers],
            "dimensions": [round(v, 4) for v in o.dimensions],
            "bbox": [[round(v, 4) for v in bb[0]], [round(v, 4) for v in bb[1]]] if bb else None,
            "parent": o.parent.name if o.parent else None,
            "children": [c.name for c in o.children],
            "collections": [path(c) if c.name in parents else "<scene root>" for c in o.users_collection],
            "section": _section_name(sm.section_of_object(o)),
            "instances": o.instance_collection.name if o.instance_type == "COLLECTION" and o.instance_collection else None,
            "locked": _locked(o),
        }
        if o.type == "MESH":
            info["verts"] = len(o.data.vertices)
        if o.type in GEOMETRY:
            tile += 1
            info["tile"] = tile
        objects.append(info)

    def tree(c):
        return {"name": c.name, "section": bool(sm.section_id_of(c)), "objects": len(c.objects),
                "children": [tree(ch) for ch in c.children]}

    data = {
        "source_blend": bpy.data.filepath,
        "blender_bin": bpy.app.binary_path,
        "unit_scale": scene.unit_settings.scale_length,
        "collections": tree(scene.collection),
        "objects": objects,
    }
    with open(os.path.join(out, "scene.json"), "w") as f:
        json.dump(data, f, indent=2)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "source.blend"), copy=True, relative_remap=False)
    return {"dir": out, "blender_bin": bpy.app.binary_path, "source_blend": bpy.data.filepath,
            "objects": len(objects), "tiles": tile, "unsaved_changes": bpy.data.is_dirty}


# ---------------------------------------------------------------- apply

def _resolve(path_names, parents):
    """Walk a collection path. Returns (existing collections, names still to create, error)."""
    have, cur = [], bpy.context.scene.collection
    for i, n in enumerate(path_names):
        c = bpy.data.collections.get(n)
        if c is None:
            return have, list(path_names[i:]), None
        if c.library or c.override_library:
            return have, [], "collection %s is linked from another file" % n
        if c.name not in [ch.name for ch in cur.children]:
            where = sm.collection_path(c, parents) if c.name in parents else "outside this scene"
            return have, [], "collection %s exists at %s, not under %s" % (n, where, cur.name)
        have.append(c)
        cur = c
    return have, [], None


def _section_at(have, parents):
    """Owning section of a collection path's deepest existing collection (new ones inherit it)."""
    if not have:
        return None
    cur = have[-1]
    while cur is not None:
        if sm.section_id_of(cur):
            return cur
        cur = parents.get(cur.name)
    return None


def _check(plan):
    parents = sm.collection_parents()
    instanced = _instanced_collections()
    errors, steps = [], []
    entries = plan.get("objects", [])
    names = [e.get("name") for e in entries]
    for n in {n for n in names if names.count(n) > 1}:
        errors.append("%s is listed more than once" % n)
    renamed_away = {e["name"] for e in entries if e.get("new_name") and e["new_name"] != e.get("name")}
    new_names = [e["new_name"] for e in entries if e.get("new_name")]
    for n in {n for n in new_names if new_names.count(n) > 1}:
        errors.append("new name %s is used more than once" % n)

    for e in entries:
        obj = bpy.data.objects.get(e.get("name", ""))
        if obj is None:
            errors.append("no object named %r" % e.get("name"))
            continue
        why = _locked(obj)
        if why:
            errors.append("%s: %s, leave it out" % (obj.name, why))
            continue
        new = e.get("new_name")
        if new is not None and new != obj.name:
            if not new or len(new.encode()) > 63:
                errors.append("%s: new name %r is empty or longer than 63 bytes" % (obj.name, new))
            elif new.startswith(LOCKED_PREFIXES):
                errors.append("%s: new name %s uses the pipeline prefix ctx_/CTX_" % (obj.name, new))
            elif bpy.data.objects.get(new) is not None and new not in renamed_away:
                errors.append("%s: name %s is taken by an object not being renamed" % (obj.name, new))
        coll_path = e.get("collection")
        target = None
        if coll_path is not None:
            if not coll_path or not all(isinstance(p, str) and p for p in coll_path):
                errors.append("%s: collection path %r is not a list of names" % (obj.name, coll_path))
                continue
            have, create, err = _resolve(coll_path, parents)
            if err:
                errors.append("%s: %s" % (obj.name, err))
                continue
            if any(n.startswith(LOCKED_PREFIXES) for n in create):
                errors.append("%s: new collection names can't use the pipeline prefix ctx_/CTX_" % obj.name)
                continue
            before, after = sm.section_of_object(obj), _section_at(have, parents)
            if before != after:
                errors.append("%s: would move from section %s to %s; objects stay in their section"
                              % (obj.name, _section_name(before) or "(none)", _section_name(after) or "(none)"))
                continue
            leaving = [c.name for c in obj.users_collection if c.name in instanced]
            if leaving:
                errors.append("%s: would leave %s, which another object instances" % (obj.name, ", ".join(leaving)))
                continue
            target = (have, create)
        steps.append((obj, new if new and new != obj.name else None, target))
    return errors, steps


def _undo_push(msg):
    try:
        bpy.ops.ed.undo_push(message=msg)
    except Exception:  # noqa: BLE001 - no undo stack in background mode
        pass


def apply(plan_path, dry_run=False, backup=True):
    with open(plan_path) as f:
        plan = json.load(f)
    errors, steps = _check(plan)
    if errors:
        return {"ok": False, "errors": errors}
    if dry_run:
        return {"ok": True, "dry_run": True, "renames": sum(1 for s in steps if s[1]),
                "moves": sum(1 for s in steps if s[2])}

    backup_path = None
    if backup:
        if not bpy.data.filepath:
            return {"ok": False, "errors": ["Save the open file first, so there is something to back up."]}
        root, ext = os.path.splitext(bpy.data.filepath)
        backup_path = "%s.ctx-backup-%s%s" % (root, datetime.datetime.now().strftime("%Y%m%d-%H%M%S"), ext)
        bpy.ops.wm.save_as_mainfile(filepath=backup_path, copy=True)
    _undo_push("Context: before organize")

    parents = sm.collection_parents()
    had_objects = {c.name for c in bpy.data.collections if len(c.objects)}
    renamed, moved, created = [], [], []

    # Renames: two passes through temp names, so swaps and chains don't pick up .001.
    for i, (obj, new, _t) in enumerate(steps):
        if new:
            renamed.append([obj.name, new])
            obj.name = "__ctx_organize_%d" % i
    for obj, new, _t in steps:
        if new:
            obj.name = new

    for obj, _new, target in steps:
        if not target:
            continue
        have, create = target
        cur = have[-1] if have else bpy.context.scene.collection
        for n in create:
            c = bpy.data.collections.get(n)
            if c is None or c.name not in [ch.name for ch in cur.children]:
                c = bpy.data.collections.new(n)
                cur.children.link(c)
                created.append(sm.collection_path(c, sm.collection_parents()))
            cur = c
        before = [sm.collection_path(c, parents) if c.name in parents else "<scene root>" for c in obj.users_collection]
        if cur.name not in [c.name for c in obj.users_collection]:
            cur.objects.link(obj)
        for c in list(obj.users_collection):
            if c != cur:
                c.objects.unlink(obj)
        moved.append([obj.name, before, sm.collection_path(cur, sm.collection_parents()) if cur != bpy.context.scene.collection else "<scene root>"])

    _undo_push("Context: organize")
    wrong = [new for obj, new, _t in steps if new and obj.name != new]
    emptied = sorted(n for n in had_objects if n in bpy.data.collections
                     and not len(bpy.data.collections[n].objects) and not len(bpy.data.collections[n].children))
    report = {"ok": not wrong, "backup": backup_path, "renamed": renamed, "moved": moved,
              "created_collections": created, "emptied_collections": emptied}
    if wrong:
        report["errors"] = ["rename to %s didn't take" % w for w in wrong]
    with open(os.path.join(os.path.dirname(os.path.abspath(plan_path)), "report.json"), "w") as f:
        json.dump(report, f, indent=2)
    return report


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:]
    if argv[0] == "apply":
        r = apply(argv[1], dry_run="--dry-run" in argv, backup="--save" in argv)
        print("CTX_ORGANIZE " + json.dumps(r))
        if r["ok"] and "--save" in argv:
            bpy.ops.wm.save_mainfile()
        sys.exit(0 if r["ok"] else 2)
    elif argv[0] == "inspect":
        print("CTX_ORGANIZE " + json.dumps(inspect(argv[1])))
