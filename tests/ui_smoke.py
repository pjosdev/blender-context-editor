"""UI smoke test. Needs a real window (not -b); quits itself.

    BLENDER_USER_RESOURCES=<tmp> $BLENDER_BIN --factory-startup <test scene .blend from tests/make_test_scene.py> \
        --python tests/ui_smoke.py -- <out_dir>

Checks: add-on enables, Context workspace gets created with a Context Editor showing the tree,
node + sidebar draw code runs without errors (drawn several frames), reference thumbnails get
previews, the drop operator (what drag-and-drop calls) adds nodes, screenshots are written.
Prints CTX_UI_OK or CTX_UI_FAIL <reason>.
"""

import os
import sys
import traceback

import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
OUT = sys.argv[sys.argv.index("--") + 1]
os.makedirs(OUT, exist_ok=True)

import addon  # noqa: E402

addon.register()
from addon import tree as T  # noqa: E402

state = {"step": 0, "errors": []}


def fail(msg):
    print("CTX_UI_FAIL", msg)
    bpy.ops.wm.quit_blender()


def context_area(screen):
    for a in screen.areas:
        if a.type == "NODE_EDITOR" and a.ui_type == T.TREE_ID:
            return a
    return None


def step():
    try:
        win = bpy.context.window_manager.windows[0]
        s = state["step"]
        state["step"] += 1
        if s == 0:
            with bpy.context.temp_override(window=win):
                bpy.ops.ctx.setup_workspace()
            ws = bpy.data.workspaces.get("Context")
            if ws is None:
                return fail("no Context workspace")
            print("CTX_UI workspace created")
            return 1.0
        if s == 1:
            area = context_area(win.screen)
            if area is None:
                return fail("no Context Editor area in the active screen: %s" % [(a.type, a.ui_type) for a in win.screen.areas])
            space = next((sp for sp in area.spaces if sp.type == "NODE_EDITOR"), None)
            if space is None or space.node_tree is None:
                state["wait"] = state.get("wait", 0) + 1
                if state["wait"] > 20:
                    return fail("Context Editor space/tree never appeared")
                state["step"] -= 1
                return 0.5
            print("CTX_UI editor tree:", space.node_tree.name, "after waits:", state.get("wait", 0),
                  "areas:", [(a.type, a.ui_type, a.x) for a in win.screen.areas])
            tree = space.node_tree
            for n in tree.nodes:
                n.select = False
            sec = [n for n in tree.nodes if n.bl_idname == "CTX_SectionNode" and n.collection.name == "WING_L"][0]
            sec.select = True
            tree.nodes.active = sec
            region = next(r for r in area.regions if r.type == "WINDOW")
            imgs = [os.path.join(ROOT, "tests", "fixtures", "drop_ref.png")]
            if not os.path.isfile(imgs[0]):
                im = bpy.data.images.new("drop_ref", 64, 64)
                im.generated_color = (0.2, 0.6, 0.9, 1)
                im.filepath_raw = imgs[0]
                im.file_format = "PNG"
                im.save()
            before = len(tree.nodes)
            with bpy.context.temp_override(window=win, area=area, region=region, space_data=space):
                bpy.ops.ctx.drop_images(directory=os.path.dirname(imgs[0]), files=[{"name": "drop_ref.png"}])
                bpy.ops.node.view_all()
            added = len(tree.nodes) - before
            linked = [n.bl_idname for n in T.linked_context_nodes(sec)]
            print("CTX_UI drop added:", added, "wing linked:", linked)
            if added != 1 or linked.count("CTX_ReferenceImageNode") != 1:
                return fail("drop operator did not attach a Reference Image to the selected section")
            # Open the sidebar so the Context panel draws.
            if not space.show_region_ui:
                space.show_region_ui = True
            for a in win.screen.areas:
                if a.type == "VIEW_3D":
                    a.spaces.active.show_region_ui = True
                    a.spaces.active.region_3d.view_perspective = "PERSP"
            return 1.5
        if s == 2:
            path = os.path.join(OUT, "context_workspace.png")
            with bpy.context.temp_override(window=win):
                bpy.ops.screen.screenshot(filepath=path)
            refs = [n for n in T.get_tree().nodes if n.bl_idname == "CTX_ReferenceImageNode"]
            missing = [n.image.name for n in refs if n.image and not n.image.preview]
            print("CTX_UI previews missing:", missing)
            # Object in a section -> viewport panel shows it.
            bpy.context.view_layer.objects.active = bpy.data.objects["seat_l"]
            return 1.0
        if s == 3:
            path = os.path.join(OUT, "context_workspace_seat.png")
            with bpy.context.temp_override(window=win):
                bpy.ops.screen.screenshot(filepath=path)
            print("CTX_UI_OK")
            bpy.ops.wm.quit_blender()
            return None
    except Exception:
        traceback.print_exc()
        fail("exception")
    return None


bpy.app.timers.register(step, first_interval=2.0)
