"""Preview renders: fixed EEVEE rig, section framing.

Importable (render_section / render_model) and runnable:

    blender -b --factory-startup base.blend --python preview.py -- \
        --blockout <run_dir>

renders previews/blockout/<id>.png for every section in <run_dir>/context.json.
The preview rig is added in memory only; callers never save after rendering.
"""

import math
import os
import sys

import bpy
import mathutils

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scene_model as sm  # noqa: E402

RIG_PREFIX = "ctx_preview_"


def _setup_render(scene, out_path, res, samples):
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = samples
    scene.render.resolution_x = res
    scene.render.resolution_y = res
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = os.path.abspath(out_path)


def _add_rig(scene):
    """Same lights and world every time, so iterations compare."""
    world = bpy.data.worlds.new(RIG_PREFIX + "world")
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.05, 0.055, 0.06, 1.0)
        bg.inputs[1].default_value = 1.0
    scene.world = world
    for name, energy, rot in (
        ("key", 3.0, (math.radians(50), 0, math.radians(35))),
        ("fill", 0.8, (math.radians(65), 0, math.radians(-120))),
        ("rim", 1.5, (math.radians(-60), 0, math.radians(170))),
    ):
        ld = bpy.data.lights.new(RIG_PREFIX + name, "SUN")
        ld.energy = energy
        ld.angle = math.radians(8)
        lo = bpy.data.objects.new(RIG_PREFIX + name, ld)
        lo.rotation_euler = rot
        scene.collection.objects.link(lo)


def _model_center(scene):
    objs = [o for o in scene.objects if o.type in {"MESH", "CURVE", "SURFACE", "FONT", "META"}
            and not o.name.startswith(RIG_PREFIX)]
    bb = sm.world_bbox(objs)
    if bb is None:
        return None
    return (mathutils.Vector(bb[0]) + mathutils.Vector(bb[1])) / 2


def _outward_azimuth(scene, bbox, turn_deg=35.0):
    """Azimuth that looks at the section from the outside of the model, turned to three-quarter."""
    center = (mathutils.Vector(bbox[0]) + mathutils.Vector(bbox[1])) / 2
    mc = _model_center(scene)
    if mc is None:
        return 45.0
    d = center - mc
    d.z = 0
    if d.length < 1e-3:
        return 45.0
    # direction = (sin az, -cos az)
    return math.degrees(math.atan2(d.x, -d.y)) + turn_deg


def _auto_camera(scene, bbox, azimuth_deg=45.0, elevation_deg=28.0, margin=1.25):
    lo, hi = (mathutils.Vector(v) for v in bbox)
    center = (lo + hi) / 2
    radius = max((hi - lo).length / 2, 0.05) * margin
    cd = bpy.data.cameras.new(RIG_PREFIX + "cam")
    cd.lens = 50
    cd.clip_start = max(radius / 1000, 0.001)
    cd.clip_end = radius * 100
    cam = bpy.data.objects.new(RIG_PREFIX + "cam", cd)
    scene.collection.objects.link(cam)
    fov = cd.angle
    dist = radius / math.sin(fov / 2)
    az, el = math.radians(azimuth_deg), math.radians(elevation_deg)
    direction = mathutils.Vector((math.cos(el) * math.sin(az), -math.cos(el) * math.cos(az), math.sin(el)))
    cam.location = center + direction * dist
    cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
    return cam


def _render(scene, cam, out_path, res, samples):
    _setup_render(scene, out_path, res, samples)
    scene.camera = cam
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    bpy.ops.render.render(write_still=True)
    return os.path.abspath(out_path)


def render_section(section_id, out_path, res=1024, samples=16):
    scene = bpy.context.scene
    coll = sm.find_section_collection(section_id)
    if coll is None:
        raise RuntimeError("no collection with ctx_section_id=%s" % section_id)
    _add_rig(scene)
    cam = bpy.data.objects.get("CTX_CAM_" + coll.name)
    if cam is None or cam.type != "CAMERA":
        bbox = sm.world_bbox([o for o in sm.owned_objects(coll) if o.type != "GREASEPENCIL"])
        if bbox is None:
            raise RuntimeError("section %s has no objects to frame" % coll.name)
        cam = _auto_camera(scene, bbox, azimuth_deg=_outward_azimuth(scene, bbox), elevation_deg=32.0)
    return _render(scene, cam, out_path, res, samples)


def render_model(out_path, res=1024, samples=16):
    scene = bpy.context.scene
    _add_rig(scene)
    cam = bpy.data.objects.get("CTX_CAM_MODEL")
    if cam is None or cam.type != "CAMERA":
        objs = [o for o in scene.objects if o.type in {"MESH", "CURVE", "SURFACE", "FONT", "META"}]
        cam = _auto_camera(scene, sm.world_bbox(objs), azimuth_deg=35.0, elevation_deg=24.0)
    return _render(scene, cam, out_path, res, samples)


def _strokes_bbox(path):
    import json

    with open(path) as f:
        data = json.load(f)
    pts = [p for layer in data["layers"] for st in layer["strokes"] for p in st["points"]]
    if not pts:
        return None
    return tuple(min(p[i] for p in pts) for i in range(3)), tuple(max(p[i] for p in pts) for i in range(3))


def _union(a, b):
    if a is None or b is None:
        return a or b
    return (tuple(min(a[0][i], b[0][i]) for i in range(3)), tuple(max(a[1][i], b[1][i]) for i in range(3)))


def _show(obj, scene):
    """Make a Grease Pencil object render (in memory only)."""
    if obj.name not in scene.objects:
        scene.collection.objects.link(obj)
    obj.hide_render = False
    obj.hide_viewport = False


def render_sketch(section_id, object_name, strokes_path, out_path, res=1024, samples=16):
    """The section (or the whole model, for a project sketch) with the drawing visible."""
    scene = bpy.context.scene
    obj = bpy.data.objects.get(object_name)
    if obj is None:
        raise RuntimeError("no object %s" % object_name)
    _show(obj, scene)
    _add_rig(scene)
    sbox = _strokes_bbox(strokes_path)
    cam = None
    if section_id:
        coll = sm.find_section_collection(section_id)
        cam = bpy.data.objects.get("CTX_CAM_" + coll.name) if coll else None
        if cam is None or cam.type != "CAMERA":
            box = _union(sm.world_bbox([o for o in sm.owned_objects(coll) if o.type != "GREASEPENCIL"]), sbox)
            cam = _auto_camera(scene, box, azimuth_deg=_outward_azimuth(scene, box), elevation_deg=32.0)
    else:
        cam = bpy.data.objects.get("CTX_CAM_MODEL")
        if cam is None or cam.type != "CAMERA":
            cam = _auto_camera(scene, sbox or sm.world_bbox(list(scene.objects)), azimuth_deg=35.0,
                               elevation_deg=24.0, margin=1.6)
    return _render(scene, cam, out_path, res, samples)


def _main(argv):
    import json

    args = argv[argv.index("--") + 1:] if "--" in argv else []
    if not args or args[0] != "--blockout":
        print("usage: preview.py -- --blockout <run_dir>")
        sys.exit(1)
    run_dir = os.path.abspath(args[1])
    with open(os.path.join(run_dir, "context.json")) as f:
        ctx = json.load(f)
    sketches = list(sm.iter_sketches(ctx))
    sketch_objects = {sk["object"] for _, sk in sketches}
    # Each render adds the rig again; reopen between renders for a clean state.
    blend = bpy.data.filepath
    for s in ctx["sections"]:
        bpy.ops.wm.open_mainfile(filepath=blend)
        for name in sketch_objects:  # the block-out preview shows the block-out only
            o = bpy.data.objects.get(name)
            if o is not None:
                o.hide_render = True
        render_section(s["id"], os.path.join(run_dir, s["blockout_preview"]))
        print("CTX_PREVIEW", s["id"], s["blockout_preview"])
    for sid, sk in sketches:
        bpy.ops.wm.open_mainfile(filepath=blend)
        render_sketch(sid, sk["object"], os.path.join(run_dir, sk["strokes"]), os.path.join(run_dir, sk["image"]))
        print("CTX_SKETCH", sid, sk["image"])
    with open(os.path.join(run_dir, "previews", "done.json"), "w") as f:
        json.dump({"blockout": [s["blockout_preview"] for s in ctx["sections"]],
                   "sketch": [sk["image"] for _, sk in sketches]}, f)


if __name__ == "__main__":
    _main(sys.argv)
