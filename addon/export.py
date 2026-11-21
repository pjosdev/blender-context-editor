"""Export the board + scene metadata to a self-contained run folder.

runs/<timestamp>/
  context.json
  base.blend          snapshot (save_as copy; the open file is untouched)
  refs/               copies of every reference image
  previews/blockout/  one render per section, rendered by a background Blender
"""

import datetime
import json
import os
import shutil
import subprocess
import sys

import bpy

from . import scene_model as sm
from . import tree as T

SCHEMA_VERSION = "0.1"


def _hex(c):
    return "#%02X%02X%02X" % tuple(max(0, min(255, round(v * 255))) for v in c[:3])


def _ref_ext(image):
    fmt = (image.file_format or "PNG").lower()
    return {"jpeg": ".jpg", "targa": ".tga", "open_exr": ".exr", "tiff": ".tif"}.get(fmt, "." + fmt)


def copy_reference(image, refs_dir, used):
    """Copy (or write, if packed/generated) an image into refs/. Returns run-relative path."""
    base = sm.slug(os.path.splitext(image.name)[0])
    src = bpy.path.abspath(image.filepath, library=image.library) if image.filepath else ""
    ext = os.path.splitext(src)[1].lower() if src else _ref_ext(image)
    name = base + ext
    i = 1
    while name in used:
        name = "%s_%d%s" % (base, i, ext)
        i += 1
    used.add(name)
    dst = os.path.join(refs_dir, name)
    if image.packed_file is not None:
        with open(dst, "wb") as f:
            f.write(image.packed_file.data)
    elif src and os.path.isfile(src):
        shutil.copy2(src, dst)
    else:
        # Generated or missing on disk: write the pixels out.
        img = image.copy()
        img.filepath_raw = dst
        img.file_format = "PNG" if ext == ".png" else img.file_format
        img.save()
        bpy.data.images.remove(img)
    return "refs/" + name


def _frame_chain(node):
    """Frames around ``node``, outermost first."""
    chain = []
    f = node.parent
    while f is not None:
        if f.bl_idname == "NodeFrame":
            chain.append(f)
        f = f.parent
    return list(reversed(chain))


def _new_group(label=None):
    g = {"refs": [], "notes": [], "links": [], "sketches": [], "groups": []}
    if label is not None:
        g = {"label": label, **g}
    return g


def grease_pencil_strokes(obj):
    """World-space stroke points of a Grease Pencil object, visible layers, current frame."""
    layers = []
    for layer in obj.data.layers:
        if layer.hide:
            continue
        frame = layer.current_frame()
        if frame is None or frame.drawing is None:
            continue
        m = obj.matrix_world @ layer.matrix_local
        mats = obj.data.materials
        strokes = []
        for st in frame.drawing.strokes:
            mat = mats[st.material_index] if 0 <= st.material_index < len(mats) else None
            strokes.append({
                "material": mat.name if mat else None,
                "points": [[round(v, 4) for v in (m @ p.position)] for p in st.points],
            })
        layers.append({"name": layer.name, "strokes": strokes})
    return {"object": obj.name, "layers": layers}


def write_sketch(obj, run_dir, target_key, written):
    """strokes JSON (once per object) + the path its render will be written to."""
    slug = sm.slug(obj.name)
    strokes = "sketches/%s.json" % slug
    if obj.name not in written:
        written.add(obj.name)
        os.makedirs(os.path.join(run_dir, "sketches"), exist_ok=True)
        with open(os.path.join(run_dir, strokes), "w") as f:
            json.dump(grease_pencil_strokes(obj), f)
    return {"object": obj.name, "image": "previews/sketch/%s_%s.png" % (target_key, slug), "strokes": strokes}


def _context_payload(nodes, refs_dir, used, target_key="project", written=None):
    """Context linked into a node, grouped the way the artist framed it.

    Returns {"refs", "notes", "links", "sketches", "groups"}: items outside any frame at the top,
    and one group per frame (nested frames nest), labelled with the frame's label.
    Items in the same group belong together.
    """
    root = _new_group()
    by_frame = {}

    def container(node):
        cur = root
        for f in _frame_chain(node):
            key = f.name
            if key not in by_frame:
                g = _new_group(f.label or f.name)
                g["_y"] = -f.location.y
                cur["groups"].append(g)
                by_frame[key] = g
            cur = by_frame[key]
        return cur

    for n in nodes:
        if n.bl_idname == "CTX_ReferenceImageNode" and n.image:
            container(n)["refs"].append({
                "file": copy_reference(n.image, refs_dir, used),
                "image": n.image.name,
            })
        elif n.bl_idname == "CTX_NoteNode" and n.full_text():
            container(n)["notes"].append({"name": n.text_block.name, "text": n.full_text()})
        elif n.bl_idname == "CTX_LinkNode" and n.url:
            container(n)["links"].append({"url": n.url, "label": n.label})
        elif n.bl_idname == "CTX_GreasePencilNode" and n.object:
            run_dir = os.path.dirname(refs_dir)
            container(n)["sketches"].append(
                write_sketch(n.object, run_dir, target_key, written if written is not None else set()))

    def tidy(g):
        g["groups"].sort(key=lambda x: x.pop("_y", 0))
        for sub in g["groups"]:
            tidy(sub)
    tidy(root)
    return root


def _object_info(o):
    bb = sm.world_bbox([o])
    info = {
        "name": o.name,
        "type": o.type,
        "vertex_count": len(o.data.vertices) if o.type == "MESH" else 0,
        "bbox_world": {"min": [round(v, 4) for v in bb[0]], "max": [round(v, 4) for v in bb[1]]} if bb else None,
        "materials": [s.material.name for s in o.material_slots if s.material],
    }
    return info


def build_context(scene, run_dir):
    tree = T.get_tree(create=False)
    if tree is None:
        raise RuntimeError("No Context Editor tree in this file")
    refs_dir = os.path.join(run_dir, "refs")
    os.makedirs(refs_dir, exist_ok=True)
    used = set()
    written = set()
    parents = sm.collection_parents(scene)

    proj = T.project_node(tree)
    project = {"style_notes": "", "era": "", "scale_unit": "m", "palette": [],
               "global_refs": [], "global_notes": [], "global_links": [], "global_sketches": [],
               "global_groups": []}
    if proj:
        g = _context_payload(T.linked_context_nodes(proj), refs_dir, used, "project", written)
        project.update({
            "style_notes": proj.style_notes.as_string().strip() if proj.style_notes else "",
            "era": proj.era,
            "scale_unit": proj.scale_unit,
            "palette": [_hex(p.color) for p in proj.palette],
            "global_refs": g["refs"],
            "global_notes": g["notes"],
            "global_links": g["links"],
            "global_sketches": g["sketches"],
            "global_groups": g["groups"],
        })

    # Drawings linked into the board are context, not block-out.
    sketch_objs = {n.object.name for n in tree.nodes if n.bl_idname == "CTX_GreasePencilNode" and n.object}
    sections = []
    boxes = {}
    for node in T.section_nodes(tree):
        coll = node.collection
        if coll is None:
            continue
        sid = sm.ensure_section_id(coll)
        node.section_id = sid
        c = _context_payload(T.linked_context_nodes(node), refs_dir, used, sid[:6], written)
        objs = sorted((o for o in sm.owned_objects(coll) if o.name not in sketch_objs), key=lambda o: o.name)
        boxes[sid] = sm.world_bbox(objs)
        sections.append({
            "id": sid,
            "title": node.title or coll.name,
            "collection": coll.name,
            "collection_path": sm.collection_path(coll, parents),
            "parent_id": sm.parent_section_id(coll, parents),
            "depth": sm.section_depth(coll, parents),
            "status": node.status,
            "order": node.order,
            "prefix": sm.prefix_for(sid),
            "intent": node.intent.as_string().strip() if node.intent else "",
            "refs": c["refs"],
            "notes": c["notes"],
            "links": c["links"],
            "sketches": c["sketches"],
            "groups": c["groups"],
            "objects": [_object_info(o) for o in objs],
            "blockout_preview": "previews/blockout/%s.png" % sid,
            "neighbors": [],
        })

    # Neighbors: bounding boxes that touch, with a tolerance of 1% of the model size.
    all_box = sm.world_bbox([o for o in scene.objects])
    tol = 0.01 * max((all_box[1][i] - all_box[0][i]) for i in range(3)) if all_box else 0.01
    for s in sections:
        s["neighbors"] = sorted(
            o["id"] for o in sections
            if o["id"] != s["id"]
            and o["id"] != s["parent_id"] and s["id"] != o["parent_id"]
            and sm.bboxes_touch(boxes[s["id"]], boxes[o["id"]], tol)
        )
    sections.sort(key=lambda s: (s["depth"], s["order"], s["collection_path"]))

    return {
        "schema_version": SCHEMA_VERSION,
        "exported_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "source_blend": bpy.data.filepath,
        "blender_version": bpy.app.version_string,
        "blender_bin": bpy.app.binary_path,
        "python_bin": sys.executable,
        "addon_dir": os.path.dirname(os.path.abspath(__file__)),
        "scene": scene.name,
        "project": project,
        "sections": sections,
    }


def runs_root(scene):
    root = scene.ctx_runs_dir or "//runs"
    return os.path.abspath(bpy.path.abspath(root))


def run_name(blend_path, now=None):
    """Run folder name: ``<YYYY-MM-DD>_<HHMM>_<file>``, e.g. ``2026-11-20_1318_bikething``.

    Date first so names sort by time. ``tools/name_run.py`` later appends the model that built it
    (``_opus-xhigh``)."""
    now = now or datetime.datetime.now()
    stem = os.path.splitext(os.path.basename(blend_path))[0]
    slug = "".join(c if c.isalnum() else "-" for c in stem.lower()).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return "%s_%s" % (now.strftime("%Y-%m-%d_%H%M"), slug or "untitled")


def export_run(scene, render_previews=True, runs_dir=None):
    """Snapshot the board and scene into a new run folder under ``runs_dir`` (default: the scene's).

    Previews render in a background Blender; it writes previews/done.json when it finishes
    and its pid is in previews/render.pid.
    """
    if not bpy.data.filepath:
        raise RuntimeError("Save the .blend file before exporting")
    root = os.path.abspath(runs_dir) if runs_dir else runs_root(scene)
    name = run_name(bpy.data.filepath)
    run_dir, n = os.path.join(root, name), 2
    while os.path.exists(run_dir):  # two snapshots in the same minute
        run_dir, n = os.path.join(root, "%s-%d" % (name, n)), n + 1
    os.makedirs(os.path.join(run_dir, "previews", "blockout"), exist_ok=True)
    os.makedirs(os.path.join(run_dir, "previews", "sketch"), exist_ok=True)

    ctx = build_context(scene, run_dir)
    # Section ids were just ensured on the collections; mirror them into the snapshot.
    base = os.path.join(run_dir, "base.blend")
    bpy.ops.wm.save_as_mainfile(filepath=base, copy=True, relative_remap=False)
    with open(os.path.join(run_dir, "context.json"), "w") as f:
        json.dump(ctx, f, indent=2)

    proc = None
    if render_previews and (ctx["sections"] or any(sm.iter_sketches(ctx))):
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "preview.py")
        log = open(os.path.join(run_dir, "previews", "blockout", "render.log"), "w")
        proc = subprocess.Popen(
            [bpy.app.binary_path, "-b", "--factory-startup", base, "--python", script, "--", "--blockout", run_dir],
            stdout=log, stderr=subprocess.STDOUT,
            # Windows: blender.exe is a console program; don't pop a console window over the artist's Blender.
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        with open(os.path.join(run_dir, "previews", "render.pid"), "w") as f:
            f.write(str(proc.pid))
    return run_dir, ctx, proc
