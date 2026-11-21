"""Datablock fingerprints and ownership, for the before/after diff in run_script.py.

The touched log is computed from what actually changed in bpy.data, never
self-reported by the build script.
"""

import hashlib
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scene_model as sm  # noqa: E402

# bpy.data collections that are diffed.
DATA_KINDS = (
    "objects", "meshes", "curves", "materials", "node_groups", "lights", "cameras",
    "images", "textures", "collections", "worlds", "scenes", "lattices", "metaballs",
    "fonts", "armatures", "actions", "hair_curves", "pointclouds", "volumes",
    "grease_pencils", "particles", "texts",
)

SKIP_PROPS = {
    "rna_type", "session_uid", "users", "is_evaluated", "original", "tag", "is_runtime_data",
    "preview", "use_extra_user", "is_missing", "bl_rna", "id_data", "is_editmode",
    "select", "is_dirty", "bindcode", "is_float", "has_data", "frame_duration",
    "use_fake_user", "is_embedded_data", "is_library_indirect", "name_full",
    "library_weak_reference", "override_library", "asset_data",
}
# Derived or UI state that changes as a side effect of normal work.
SKIP_BY_TYPE = {
    "Scene": {"objects", "view_layers", "tool_settings", "cursor", "statistics",
              "sequence_editor", "timeline_markers", "keying_sets_all", "transform_orientation_slots"},
    "Object": {"bound_box", "mode", "field", "collision", "soft_body", "rigid_body", "particle_systems",
               "users_collection", "users_scene", "children", "children_recursive", "motion_path",
               "image_user", "shader_effects", "lineart", "light_linking"},
    "Collection": {"all_objects", "children_recursive", "users_dimensions", "collection_objects",
                   "collection_children", "exporters"},
    "Image": {"pixels", "size", "frame_duration", "render_slots", "bindcode", "packed_files",
              "is_dirty", "has_data", "depth", "channels", "bindcode"},
    "Material": {"paint_active_slot", "texture_paint_images", "texture_paint_slots"},
}
MESH_HEAVY = {"vertices", "edges", "polygons", "loops", "loop_triangles", "loop_triangle_polygons",
              "attributes", "color_attributes", "uv_layers", "vertex_normals", "polygon_normals",
              "corner_normals", "vertex_colors", "vertex_creases", "edge_creases", "skin_vertices",
              "shape_keys", "normals_domain", "vertex_paint_mask", "face_maps", "cycles"}


def _num(v):
    if isinstance(v, float):
        return "%.5g" % v
    return repr(v)


def _rna_fp(ptr, depth, out, path=""):
    try:
        props = ptr.bl_rna.properties
    except AttributeError:
        return
    skip = SKIP_PROPS | SKIP_BY_TYPE.get(type(ptr).__name__, set())
    if isinstance(ptr, bpy.types.Mesh):
        skip = skip | MESH_HEAVY
    for p in props:
        pid = p.identifier
        if pid in skip:
            continue
        try:
            v = getattr(ptr, pid)
        except Exception:
            continue
        t = p.type
        if t in {"BOOLEAN", "INT", "FLOAT", "STRING", "ENUM"}:
            if t == "STRING" and getattr(p, "subtype", "") in {"FILE_PATH", "DIR_PATH", "BYTE_STRING"} and pid != "filepath":
                continue
            try:
                if isinstance(v, (set, frozenset)):
                    v = ",".join(sorted(v))
                elif hasattr(v, "__len__") and not isinstance(v, str):
                    v = tuple(_num(x) if not hasattr(x, "__len__") else tuple(_num(y) for y in x) for x in v)
                else:
                    v = _num(v)
            except Exception:
                v = repr(v)
            out.append("%s%s=%s" % (path, pid, v))
        elif t == "POINTER":
            if v is None:
                out.append("%s%s=None" % (path, pid))
            elif isinstance(v, bpy.types.ID) and not v.is_embedded_data:
                out.append("%s%s->%s:%s" % (path, pid, type(v).__name__, v.name))
            elif depth > 0:
                _rna_fp(v, depth - 1, out, "%s%s." % (path, pid))
        elif t == "COLLECTION" and depth > 0:
            items = list(v)[:256]
            out.append("%s%s#%d" % (path, pid, len(v)))
            for i, item in enumerate(items):
                if isinstance(item, bpy.types.ID) and not item.is_embedded_data:
                    out.append("%s%s[%d]->%s" % (path, pid, i, item.name))
                else:
                    _rna_fp(item, depth - 1, out, "%s%s[%d]." % (path, pid, i))


def _mesh_extra(me, out):
    import array

    out.append("counts=%d/%d/%d" % (len(me.vertices), len(me.edges), len(me.polygons)))
    co = array.array("f", [0.0]) * (len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    out.append("co=" + hashlib.sha1(bytes(array.array("f", (round(x, 5) for x in co)))).hexdigest())
    idx = array.array("i", [0]) * len(me.loops)
    me.loops.foreach_get("vertex_index", idx)
    out.append("loops=" + hashlib.sha1(bytes(idx)).hexdigest())
    mi = array.array("i", [0]) * len(me.polygons)
    if len(me.polygons):
        me.polygons.foreach_get("material_index", mi)
    out.append("mat_index=" + hashlib.sha1(bytes(mi)).hexdigest())
    out.append("attrs=" + ",".join(sorted("%s:%s:%s" % (a.name, a.domain, a.data_type) for a in me.attributes)))
    out.append("uvs=" + ",".join(u.name for u in me.uv_layers))


def fingerprint(idb):
    out = []
    _rna_fp(idb, 3, out)
    if isinstance(idb, bpy.types.Mesh):
        _mesh_extra(idb, out)
    if isinstance(idb, bpy.types.Object):
        out.append("matrix_world=" + ",".join(_num(x) for row in idb.matrix_world for x in row))
        out.append("in=" + ",".join(sorted(c.name for c in idb.users_collection)))
    return hashlib.sha1("\n".join(out).encode("utf-8", "replace")).hexdigest()


def snapshot():
    """{"kind/name": fingerprint} over every diffed datablock."""
    snap = {}
    for kind in DATA_KINDS:
        coll = getattr(bpy.data, kind, None)
        if coll is None:
            continue
        for idb in coll:
            if idb.library is not None:
                continue
            snap["%s/%s" % (kind, idb.name)] = fingerprint(idb)
    return snap


def diff(before, after):
    created = sorted(k for k in after if k not in before)
    removed = sorted(k for k in before if k not in after)
    modified = sorted(k for k in after if k in before and before[k] != after[k])
    return created, modified, removed


# ---------------------------------------------------------------- ownership

def owned_keys(section_id):
    """Datablock keys the section owns in the current state of bpy.data.

    Owned: the section's collections and their objects; any datablock whose name
    carries the section prefix; any datablock whose every user is owned
    (so a block-out mesh or material used only inside the section is owned).
    """
    coll = sm.find_section_collection(section_id)
    prefix = sm.prefix_for(section_id)
    owned = set()
    if coll is not None:
        for c in sm.owned_collections(coll):
            owned.add("collections/" + c.name)
        for o in sm.owned_objects(coll):
            owned.add("objects/" + o.name)
    id_to_key = {}
    for kind in DATA_KINDS:
        dc = getattr(bpy.data, kind, None)
        if dc is None:
            continue
        for idb in dc:
            key = "%s/%s" % (kind, idb.name)
            id_to_key[idb] = key
            if idb.name.startswith(prefix):
                owned.add(key)
    umap = bpy.data.user_map(subset=list(id_to_key.keys()))
    changed = True
    while changed:
        changed = False
        for idb, users in umap.items():
            key = id_to_key.get(idb)
            if key is None or key in owned or key.startswith(("scenes/", "worlds/", "collections/", "objects/")):
                continue
            ukeys = [id_to_key.get(u) for u in users if u is not idb]
            ukeys = [k for k in ukeys if k is not None]
            if ukeys and all(k in owned for k in ukeys):
                owned.add(key)
                changed = True
    return owned
