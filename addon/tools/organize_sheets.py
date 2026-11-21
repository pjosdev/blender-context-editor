"""Contact sheets for organizing: every geometry object, alone and in place.

    "$BLENDER" -b --factory-startup <dir>/source.blend --python tools/organize_sheets.py -- <dir>

<dir> is the folder tools/organize.py inspect() wrote. For each object with a "tile" number in
scene.json it renders the object alone (its own materials) and the whole scene with the object
orange and the rest grey, then tiles them, numbered, into <dir>/sheet_<nn>.png (15 per sheet).
Works on the copy only; nothing is saved.
"""

import json
import os
import sys

import bpy
import numpy as np

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(TOOLS))
import preview  # noqa: E402
import scene_model as sm  # noqa: E402

RES = 256
COLS, ROWS = 3, 5
GEOMETRY = {"MESH", "CURVE", "SURFACE", "FONT", "META", "GREASEPENCIL", "CURVES"}
ORANGE = (1.0, 0.45, 0.05, 1.0)
GREY = (0.6, 0.6, 0.62, 1.0)

# 3x5 digits
DIGITS = {
    "0": "111101101101111", "1": "010110010010111", "2": "111001111100111", "3": "111001111001111",
    "4": "101101111001001", "5": "111100111001111", "6": "111100111101111", "7": "111001001001001",
    "8": "111101111101111", "9": "111101111001111",
}


def _show_everything(scene):
    def walk(lc):
        lc.exclude = False
        lc.hide_viewport = False
        lc.collection.hide_render = False
        for ch in lc.children:
            walk(ch)
    walk(scene.view_layers[0].layer_collection)


def _render(scene, cam, path):
    scene.camera = cam
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(path)
    px = np.array(img.pixels[:], dtype=np.float32).reshape(RES, RES, 4)
    bpy.data.images.remove(img)
    return px


def _bbox(objs):
    import mathutils
    pts = [o.matrix_world @ mathutils.Vector(c) for o in objs for c in o.bound_box]
    if not pts:
        return None
    lo = tuple(min(p[i] for p in pts) for i in range(3))
    hi = tuple(max(p[i] for p in pts) for i in range(3))
    return lo, hi


def _number(tile, n):
    s, x0, y0, scale = str(n), 8, 8, 5
    for i, ch in enumerate(s):
        bits = DIGITS[ch]
        for r in range(5):
            for c in range(3):
                if bits[r * 3 + c] == "1":
                    x = x0 + (i * 4 + c) * scale
                    y = tile.shape[0] - (y0 + (r + 1) * scale)  # pixels are bottom-up
                    tile[y:y + scale, x:x + scale] = (1, 1, 0.2, 1)
    return tile


def main(out_dir):
    with open(os.path.join(out_dir, "scene.json")) as f:
        objs = [o for o in json.load(f)["objects"] if o.get("tile")]
    scene = bpy.context.scene
    _show_everything(scene)
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x = scene.render.resolution_y = RES
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    sh = scene.display.shading
    sh.light = "STUDIO"
    world = bpy.data.worlds.new("ctx_sheet_world")
    world.color = (0.08, 0.085, 0.09)
    scene.world = world

    geo = [o for o in scene.objects if o.type in GEOMETRY]
    model_cam = preview._auto_camera(scene, _bbox(geo), azimuth_deg=35.0, elevation_deg=28.0, margin=1.0)
    tmp = os.path.join(out_dir, "tiles")
    os.makedirs(tmp, exist_ok=True)

    # The whole scene in grey, once; each object is laid over it in orange so it shows even when hidden inside.
    for g in geo:
        g.hide_render = False
    sh.color_type = "SINGLE"
    sh.single_color = GREY[:3]
    base = _render(scene, model_cam, os.path.join(tmp, "scene.png"))

    tiles = []
    for info in objs:
        o = bpy.data.objects.get(info["name"])
        if o is None:
            continue
        for g in geo:
            g.hide_render = g != o
        # alone, own materials
        scene.render.film_transparent = False
        sh.color_type = "MATERIAL"
        cam = preview._auto_camera(scene, _bbox([o]), azimuth_deg=35.0, elevation_deg=28.0, margin=1.15)
        alone = _render(scene, cam, os.path.join(tmp, "%d_a.png" % info["tile"]))
        bpy.data.objects.remove(cam)
        # in place: the object alone from the scene camera, over the grey scene
        scene.render.film_transparent = True
        sh.color_type = "SINGLE"
        sh.single_color = ORANGE[:3]
        over = _render(scene, model_cam, os.path.join(tmp, "%d_b.png" % info["tile"]))
        a = over[..., 3:4]
        place = base * (1 - a) + over * a
        place[..., 3] = 1
        tile = np.concatenate([alone, place], axis=1)
        tile[:, RES - 1:RES + 1] = (0, 0, 0, 1)
        tiles.append(_number(tile, info["tile"]))
    scene.render.film_transparent = False

    per = COLS * ROWS
    sheets = []
    for s in range(0, len(tiles), per):
        chunk = tiles[s:s + per]
        h, w = RES, RES * 2
        sheet = np.zeros((ROWS * h, COLS * w, 4), dtype=np.float32)
        sheet[..., 3] = 1
        for i, t in enumerate(chunk):
            r, c = divmod(i, COLS)
            y = (ROWS - 1 - r) * h  # bottom-up
            sheet[y:y + h, c * w:(c + 1) * w] = t
            sheet[y:y + h, c * w:c * w + 2] = (0, 0, 0, 1)
            sheet[y:y + 2, c * w:(c + 1) * w] = (0, 0, 0, 1)
        img = bpy.data.images.new("sheet", COLS * w, ROWS * h, alpha=True)
        img.pixels = sheet.ravel()
        path = os.path.join(out_dir, "sheet_%02d.png" % (s // per + 1))
        img.filepath_raw = path
        img.file_format = "PNG"
        img.save()
        sheets.append(path)
    print("CTX_SHEETS %d tiles, %s" % (len(tiles), " ".join(sheets)))


if __name__ == "__main__":
    main(os.path.abspath(sys.argv[sys.argv.index("--") + 1]))
