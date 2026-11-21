"""Build the test scene: a block-out shuttle with a populated board, saved to <out.blend>.

    $BLENDER_BIN -b --factory-startup --python tests/make_test_scene.py -- <out.blend>

tests/test_pipeline.py builds it in a temp folder before the tests run.

Sections: COCKPIT (with child section COCKPIT/SEATS), WING_L, ENGINES.
HULL is deliberately left untagged: no script may touch it.
Reference images are generated colour swatches, packed into the file.
"""

import math
import os
import sys

import bpy
import bmesh

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import addon  # noqa: E402

addon.register()
from addon import tree as T  # noqa: E402

OUT = os.path.abspath(sys.argv[sys.argv.index("--") + 1])


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def coll(name, parent):
    c = bpy.data.collections.new(name)
    parent.children.link(c)
    return c


def box(name, c, size, loc, mat=None):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=size, verts=bm.verts)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    o.location = loc
    c.objects.link(o)
    if mat:
        me.materials.append(mat)
    return o


def tub(name, c, size, loc, wall, mat):
    """Open-topped box: floor and four walls, so the interior reads from above."""
    sx, sy, sz = size
    bm = bmesh.new()
    parts = [
        ((sx, sy, wall), (0, 0, -sz / 2 + wall / 2)),
        ((wall, sy, sz), (-sx / 2 + wall / 2, 0, 0)),
        ((wall, sy, sz), (sx / 2 - wall / 2, 0, 0)),
        ((sx, wall, sz), (0, -sy / 2 + wall / 2, 0)),
        ((sx, wall, sz * 0.6), (0, sy / 2 - wall / 2, -sz * 0.2)),
    ]
    for s, off in parts:
        geom = bmesh.ops.create_cube(bm, size=1.0)["verts"]
        bmesh.ops.scale(bm, vec=s, verts=geom)
        bmesh.ops.translate(bm, vec=off, verts=geom)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    o.location = loc
    c.objects.link(o)
    me.materials.append(mat)
    return o


def cylinder(name, c, r, depth, loc, rot, mat):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=r, radius2=r * 0.85, depth=depth)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    o.location = loc
    o.rotation_euler = rot
    c.objects.link(o)
    me.materials.append(mat)
    return o


def wedge(name, c, mat):
    """Left wing: swept slab from the hull side outwards (-X)."""
    root_y0, root_y1, tip_y0, tip_y1 = -2.2, 1.0, -2.6, -1.4
    x0, x1, t = -1.05, -4.2, 0.18
    v = [(x0, root_y0, -t), (x0, root_y1, -t), (x1, tip_y1, -t * 0.5), (x1, tip_y0, -t * 0.5),
         (x0, root_y0, t), (x0, root_y1, t), (x1, tip_y1, t * 0.5), (x1, tip_y0, t * 0.5)]
    f = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(v, [], f)
    me.update()
    o = bpy.data.objects.new(name, me)
    o.location = (0, 0, -0.1)
    c.objects.link(o)
    me.materials.append(mat)
    return o


def swatch(name, rgb, size=256):
    img = bpy.data.images.new(name, size, size)
    px = []
    for y in range(size):
        for x in range(size):
            n = 0.9 + 0.1 * math.sin(x * 0.21) * math.sin(y * 0.17)
            px += [rgb[0] * n, rgb[1] * n, rgb[2] * n, 1.0]
    img.pixels = px
    img.pack()
    return img


def sketch(name, c, strokes):
    """Grease Pencil object with one layer; each stroke is a list of world points."""
    gp = bpy.data.grease_pencils.new(name)
    mat = bpy.data.materials.new(name + "_ink")
    bpy.data.materials.create_gpencil_data(mat)
    mat.grease_pencil.color = (0.9, 0.15, 0.1, 1.0)
    gp.materials.append(mat)
    drawing = gp.layers.new("Lines").frames.new(scene_frame()).drawing
    drawing.add_strokes([len(s) for s in strokes])
    for st, pts in zip(drawing.strokes, strokes):
        for p, co in zip(st.points, pts):
            p.position = co
            p.radius = 0.008
    o = bpy.data.objects.new(name, gp)
    c.objects.link(o)
    return o


def scene_frame():
    return bpy.context.scene.frame_current


def text(name, body):
    t = bpy.data.texts.new(name)
    t.write(body)
    return t


def main():
    reset()
    scene = bpy.context.scene
    scene.name = "Ship"
    scene.ctx_runs_dir = "//../runs"
    grey = bpy.data.materials.new("blockout_grey")
    grey.diffuse_color = (0.55, 0.55, 0.55, 1)

    ship = coll("SHIP", scene.collection)
    hull = coll("HULL", ship)
    cockpit = coll("COCKPIT", ship)
    seats = coll("SEATS", cockpit)
    wing = coll("WING_L", ship)
    engines = coll("ENGINES", ship)

    box("hull_body", hull, (2.1, 6.0, 1.3), (0, -0.6, 0), grey)
    box("hull_spine", hull, (0.8, 4.0, 0.35), (0, -1.4, 0.8), grey)
    tub("cockpit_tub", cockpit, (1.7, 1.8, 1.0), (0, 3.25, 0.25), 0.08, grey)
    box("cockpit_console", cockpit, (1.4, 0.35, 0.35), (0, 3.85, 0.15), grey)
    box("seat_l", seats, (0.5, 0.5, 0.55), (-0.38, 3.05, -0.02), grey)
    box("seat_r", seats, (0.5, 0.5, 0.55), (0.38, 3.05, -0.02), grey)
    wedge("wing_l_slab", wing, grey)
    for i, x in enumerate((-0.55, 0.55)):
        cylinder("engine_%d" % i, engines, 0.45, 1.6, (x, -4.25, 0.0), (math.radians(90), 0, 0), grey)
    box("engine_mount", engines, (1.8, 0.5, 0.7), (0, -3.55, 0.0), grey)

    # A drawing on top of the console: a row of three screens and a row of switches.
    lines = []
    for x in (-0.45, 0.0, 0.45):
        lines.append([(x - 0.17, 3.74, 0.33), (x + 0.17, 3.74, 0.33), (x + 0.17, 3.95, 0.33),
                      (x - 0.17, 3.95, 0.33), (x - 0.17, 3.74, 0.33)])
    for i in range(7):
        x = -0.54 + i * 0.18
        lines.append([(x, 3.70, 0.33), (x, 3.67, 0.33)])
    console_sketch = sketch("console sketch", cockpit, lines)

    cam_d = bpy.data.cameras.new("CTX_CAM_SEATS")
    cam_d.lens = 28
    cam = bpy.data.objects.new("CTX_CAM_SEATS", cam_d)
    import mathutils
    cam.location = (1.15, 1.75, 2.0)
    target = mathutils.Vector((0.0, 3.25, -0.05))
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.collection.objects.link(cam)

    # ---- board
    tree = T.get_tree()
    proj = T.project_node(tree)
    proj.era = "1980s industrial sci-fi"
    proj.scale_unit = "m"
    proj.style_notes = text("style_notes",
                            "Used future. Nothing is new. Function over form.\n"
                            "Panels are bolted, not sculpted. Chunky, readable at a distance.")
    for hx in ("C8B89A", "3A3F44", "E0A030"):
        p = proj.palette.add()
        p.color = tuple(int(hx[i:i + 2], 16) / 255 for i in (0, 2, 4))

    def section(c, title, order, intent, status="ready", loc=(0, 0)):
        bpy.ops.ctx.make_section(collection=c.name)
        n = T.section_node_for(tree, c)
        n.title = title
        n.order = order
        n.status = status
        n.intent = text("intent_" + c.name.lower(), intent)
        n.location = loc
        return n

    def ctx_node(node_type, target, loc, **props):
        n = tree.nodes.new(node_type)
        n.location = loc
        for k, v in props.items():
            setattr(n, k, v)
        tree.links.new(n.outputs[0], target.inputs[0])
        return n

    s_cockpit = section(cockpit, "Cockpit interior", 0,
                        "Cramped two-seat cockpit. CRT bank along the console, chunky toggle switches in rows, "
                        "beige plastic yellowed with age, gunmetal frame.", loc=(0, 400))
    s_seats = section(seats, "Cockpit seats", 1,
                      "Two bucket seats, worn beige vinyl over a gunmetal frame, five-point harness straps, "
                      "a headrest pad. Visible stitching seams.", loc=(0, 0))
    s_wing = section(wing, "Left wing", 2,
                     "Thick stubby wing with bolted access panels, panel lines, a hazard-striped leading edge "
                     "and a nav light on the tip.", loc=(0, -400))
    s_eng = section(engines, "Engine cluster", 3,
                    "Twin thrusters with ribbed nozzles, exposed piping between them, heat-scorched metal "
                    "near the exhaust, orange glow inside the nozzles.", loc=(0, -800))

    beige = swatch("ref_beige_plastic", (0.78, 0.72, 0.60))
    gun = swatch("ref_gunmetal", (0.23, 0.25, 0.27))
    amber = swatch("ref_amber_glow", (0.88, 0.63, 0.19))
    def note(name, body, target, frame=None):
        n = ctx_node("CTX_NoteNode", target, (0, 0), text_block=text(name, body))
        n.parent = frame
        return n

    def ref(img, target, frame=None):
        n = ctx_node("CTX_ReferenceImageNode", target, (0, 0), image=img)
        n.parent = frame
        return n

    def frame(label):
        f = tree.nodes.new("NodeFrame")
        f.label = label
        return f

    ref(gun, proj)
    note("avoid", "No touchscreens, no holograms, no glowing blue.", proj)
    plastic = frame("console plastic")
    ref(beige, s_cockpit, plastic)
    note("plastic notes", "This is the plastic for the CRT housings and console. Aged, yellowed, a little grimy in the corners.",
         s_cockpit, plastic)
    gpn = ctx_node("CTX_GreasePencilNode", s_cockpit, (0, 0), object=console_sketch)
    gpn.parent = plastic
    note("cockpit shape", "Leave the tub silhouette as it is; add detail on top.", s_cockpit)
    ctx_node("CTX_LinkNode", s_cockpit, (0, 0), label="Worn plastic material", url="https://example.com/worn-plastic")
    note("seats", "Seats face the console (+Y).", s_seats)
    note("wing", "No greebles on the top surface; keep it flat and readable.", s_wing)
    glow = frame("nozzle glow")
    ref(amber, s_eng, glow)
    note("glow notes", "Glow colour inside the nozzles only, not on the casing.", s_eng, glow)

    # Layout: one row per target (Project, then sections), its context nodes stacked to the left.
    heights = {"CTX_ReferenceImageNode": 380, "CTX_NoteNode": 170, "CTX_LinkNode": 190, "CTX_GreasePencilNode": 110,
               "CTX_SectionNode": 300, "CTX_ProjectNode": 280}
    y = 0
    for target in (proj, s_cockpit, s_seats, s_wing, s_eng):
        target.location = (0, y)
        stack = y
        for n in sorted(T.linked_context_nodes(target), key=lambda n: -n.location.y):
            n.location = (-340, stack)
            stack -= heights[n.bl_idname] + 30
        y = min(stack, y - heights[target.bl_idname]) - 80

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=OUT)
    print("CTX_EXAMPLE", OUT)


main()
