"""Scene model shared by the add-on and the pipeline tools.

Pure bpy + stdlib, no relative imports, so tools/ can import it by path.

Rules (also in PIPELINE.md):
- A section is a collection carrying the custom property ``ctx_section_id``.
  The id is created the moment a collection becomes a section, not at export.
- A section owns its collection, every sub-collection that is not itself a
  section, and every object in those collections.
- The parent of a section is its nearest ancestor collection that is a section.
"""

import re
import uuid

import bpy

SECTION_KEY = "ctx_section_id"


def new_section_id():
    return uuid.uuid4().hex


def prefix_for(section_id):
    return "ctx_%s_" % section_id[:6]


def slug(text):
    s = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower()
    return s or "item"


# ---------------------------------------------------------------- collections

def section_id_of(coll):
    if coll is None:
        return None
    v = coll.get(SECTION_KEY)
    return str(v) if v else None


def ensure_section_id(coll):
    sid = section_id_of(coll)
    if not sid:
        sid = new_section_id()
        coll[SECTION_KEY] = sid
    return sid


def section_collections():
    """{section_id: collection} for every tagged collection."""
    out = {}
    for c in bpy.data.collections:
        sid = section_id_of(c)
        if sid:
            out[sid] = c
    return out


def find_section_collection(section_id):
    for c in bpy.data.collections:
        if section_id_of(c) == section_id:
            return c
    return None


def collection_parents(scene=None):
    """{collection name: parent collection or None (scene root)}."""
    scene = scene or bpy.context.scene
    parents = {}

    def walk(c, parent):
        for ch in c.children:
            if ch.name not in parents:
                parents[ch.name] = parent
                walk(ch, ch)

    walk(scene.collection, None)
    return parents


def collection_path(coll, parents=None):
    parents = parents if parents is not None else collection_parents()
    parts = [coll.name]
    p = parents.get(coll.name)
    while p is not None:
        parts.append(p.name)
        p = parents.get(p.name)
    return "/".join(reversed(parts))


def parent_section_id(coll, parents=None):
    parents = parents if parents is not None else collection_parents()
    p = parents.get(coll.name)
    while p is not None:
        sid = section_id_of(p)
        if sid:
            return sid
        p = parents.get(p.name)
    return None


def section_depth(coll, parents=None):
    parents = parents if parents is not None else collection_parents()
    d = 0
    p = parents.get(coll.name)
    while p is not None:
        if section_id_of(p):
            d += 1
        p = parents.get(p.name)
    return d


def owned_collections(coll):
    """The section collection plus sub-collections that are not sections."""
    out = [coll]
    stack = list(coll.children)
    while stack:
        c = stack.pop()
        if section_id_of(c):
            continue
        out.append(c)
        stack.extend(c.children)
    return out


def owned_objects(coll):
    seen = {}
    for c in owned_collections(coll):
        for o in c.objects:
            seen[o.name] = o
    return list(seen.values())


def section_of_object(obj):
    """Innermost section that owns ``obj`` (None if untagged)."""
    best, best_depth = None, -1
    parents = collection_parents()
    for c in obj.users_collection:
        cur = c
        while cur is not None:
            sid = section_id_of(cur)
            if sid:
                d = section_depth(cur, parents)
                if d > best_depth:
                    best, best_depth = cur, d
                break
            cur = parents.get(cur.name)
    return best


# ---------------------------------------------------------------- context.json

def iter_sketches(ctx):
    """(section id or None for the project, sketch dict) for every sketch in a context export."""
    def walk(g, sid):
        for sk in g.get("sketches", []):
            yield sid, sk
        for sub in g.get("groups", []):
            yield from walk(sub, sid)

    p = ctx["project"]
    yield from walk({"sketches": p.get("global_sketches", []), "groups": p.get("global_groups", [])}, None)
    for s in ctx["sections"]:
        yield from walk(s, s["id"])


# ---------------------------------------------------------------- geometry

def world_bbox(objects):
    """(min, max) world-space corners over objects, or None."""
    import mathutils

    lo = [float("inf")] * 3
    hi = [float("-inf")] * 3
    found = False
    for o in objects:
        if o.type in {"MESH", "CURVE", "SURFACE", "FONT", "META"}:
            pts = [o.matrix_world @ mathutils.Vector(c) for c in o.bound_box]
        else:
            pts = [o.matrix_world.translation]
        for p in pts:
            found = True
            for i in range(3):
                lo[i] = min(lo[i], p[i])
                hi[i] = max(hi[i], p[i])
    if not found:
        return None
    return tuple(lo), tuple(hi)


def bboxes_touch(a, b, tol):
    if a is None or b is None:
        return False
    return all(a[0][i] - tol <= b[1][i] and b[0][i] - tol <= a[1][i] for i in range(3))
