"""Operators, sidebars and the Context workspace."""

import bpy
from bpy.props import EnumProperty, StringProperty

from . import export
from . import scene_model as sm
from . import tree as T

WORKSPACE_NAME = "Context"


def _active_collection(context):
    lc = context.view_layer.active_layer_collection
    if lc is None or lc.collection == context.scene.collection:
        return None
    return lc.collection


def _context_space(context):
    """The first Node Editor in the window showing the Context tree, if any."""
    for area in context.window.screen.areas if context.window else []:
        if area.type == "NODE_EDITOR" and area.spaces.active.tree_type == T.TREE_ID:
            return area, area.spaces.active
    return None, None


def _place_new_node(tree, near=None, offset=(-320, 0)):
    if near is not None:
        x = near.location.x + offset[0]
        siblings = T.linked_context_nodes(near)
        if not siblings:
            return (x, near.location.y)
        # Below the lowest sibling, using its drawn height (0 before first draw -> assume a thumbnail node).
        bottom = min(n.location.y - (n.dimensions.y or 300) for n in siblings)
        x = min(n.location.x for n in siblings)
        return (x, bottom - 30)
    sections = T.section_nodes(tree)
    y = min((n.location.y for n in sections), default=300) - 260
    return (0, y)


def make_section_node(context, coll):
    tree = T.get_tree()
    node = T.section_node_for(tree, coll)
    if node is None:
        node = tree.nodes.new("CTX_SectionNode")
        node.location = _place_new_node(tree)
        node.collection = coll
        node.order = len(T.section_nodes(tree)) - 1
    for n in tree.nodes:
        n.select = False
    node.select = True
    tree.nodes.active = node
    return node


def selected_section(context):
    tree = T.get_tree(create=False)
    if tree is None:
        return None
    n = tree.nodes.active
    if n is not None and n.bl_idname == "CTX_SectionNode":
        return n
    for n in tree.nodes:
        if n.select and n.bl_idname == "CTX_SectionNode":
            return n
    return None


def attach(tree, ctx_node, target):
    if target is not None:
        tree.links.new(ctx_node.outputs[0], target.inputs[0])


# ---------------------------------------------------------------- workspace

def ensure_workspace(context):
    """Create the Context workspace next to Shading: 3D view left, Context Editor right."""
    if WORKSPACE_NAME in bpy.data.workspaces:
        return bpy.data.workspaces[WORKSPACE_NAME]
    window = context.window
    if window is None:
        return None
    before = set(bpy.data.workspaces.keys())
    source = bpy.data.workspaces.get("Shading") or window.workspace
    with context.temp_override(window=window, workspace=source):
        bpy.ops.workspace.duplicate()
    new_names = set(bpy.data.workspaces.keys()) - before
    if not new_names:
        return None
    ws = bpy.data.workspaces[new_names.pop()]
    ws.name = WORKSPACE_NAME
    T.get_tree()
    # Areas only convert properly in a screen a window is showing: switch first, lay out next tick.
    window.workspace = ws
    _layout_state.update(tries=40, window=window)
    if not bpy.app.timers.is_registered(_layout_workspace):
        bpy.app.timers.register(_layout_workspace, first_interval=0.05)
    return ws


_layout_state = {"tries": 0, "window": None, "done": False}


def _layout_workspace():
    """3D view left, Context Editor right, showing the Context tree. Runs once the workspace is active."""
    st = _layout_state
    st["tries"] -= 1
    win = st["window"]
    ws = bpy.data.workspaces.get(WORKSPACE_NAME)
    if ws is None or win is None:
        return None
    try:
        screen = win.screen
    except ReferenceError:
        return None
    if win.workspace != ws:
        return 0.1 if st["tries"] > 0 else None
    if not st["done"]:
        views = [a for a in screen.areas if a.type == "VIEW_3D"]
        main = max(views or list(screen.areas), key=lambda a: a.width * a.height)
        for a in [a for a in screen.areas if a != main]:
            try:
                with bpy.context.temp_override(window=win, screen=screen, area=a):
                    bpy.ops.screen.area_close()
            except RuntimeError as e:
                print("ctx: could not close area", a.type, e)
        leftovers = [a for a in screen.areas if a != main]
        if leftovers:
            right = max(leftovers, key=lambda a: a.width * a.height)
        else:
            with bpy.context.temp_override(window=win, screen=screen, area=main):
                bpy.ops.screen.area_split(direction="VERTICAL", factor=0.5)
            halves = [main] + [a for a in screen.areas if a != main]
            right = max(halves, key=lambda a: a.x)
        with bpy.context.temp_override(window=win, screen=screen, area=right):
            right.type = "NODE_EDITOR"
            right.ui_type = T.TREE_ID
        st["done"] = True
    tree = T.get_tree(create=False)
    pending = False
    for a in screen.areas:
        if a.type == "NODE_EDITOR" and a.ui_type == T.TREE_ID:
            sp = a.spaces.active
            if sp is None or sp.type != "NODE_EDITOR":
                pending = True
            elif sp.node_tree is None and tree is not None:
                sp.node_tree = tree
    if pending and st["tries"] > 0:
        return 0.1
    st["done"] = False
    return None


class CTX_OT_setup_workspace(bpy.types.Operator):
    bl_idname = "ctx.setup_workspace"
    bl_label = "Open Context Workspace"
    bl_description = "Create (if needed) and switch to the Context workspace"

    def execute(self, context):
        T.get_tree()
        ws = ensure_workspace(context)
        if ws is None:
            self.report({"ERROR"}, "Could not create the Context workspace")
            return {"CANCELLED"}
        context.window.workspace = ws
        return {"FINISHED"}


# ---------------------------------------------------------------- operators

class CTX_OT_make_section(bpy.types.Operator):
    bl_idname = "ctx.make_section"
    bl_label = "Make Section from Active Collection"
    bl_description = "Tag the active collection as a section and add its Section node"
    bl_options = {"REGISTER", "UNDO"}

    collection: StringProperty(name="Collection", description="Collection name; empty = active collection")

    def execute(self, context):
        coll = bpy.data.collections.get(self.collection) if self.collection else _active_collection(context)
        if coll is None:
            self.report({"ERROR"}, "Make a collection active in the Outliner first")
            return {"CANCELLED"}
        first_time = T.get_tree(create=False) is None
        node = make_section_node(context, coll)
        if first_time and context.window and WORKSPACE_NAME not in bpy.data.workspaces:
            try:
                ensure_workspace(context)
            except Exception as e:  # workspace is a convenience; never block tagging
                print("ctx: workspace setup skipped:", e)
        self.report({"INFO"}, "Section: %s" % node.draw_label())
        return {"FINISHED"}


ADD_KINDS = [
    ("CTX_ReferenceImageNode", "Reference", "Reference image"),
    ("CTX_NoteNode", "Note", "Note"),
    ("CTX_LinkNode", "Link", "Link"),
    ("CTX_GreasePencilNode", "Grease Pencil", "Grease Pencil object"),
]


class CTX_OT_add_context(bpy.types.Operator):
    bl_idname = "ctx.add_context"
    bl_label = "Add Context Node"
    bl_description = "Add a context node attached to the selected section"
    bl_options = {"REGISTER", "UNDO"}

    kind: EnumProperty(items=ADD_KINDS)

    def execute(self, context):
        tree = T.get_tree()
        target = selected_section(context) or T.project_node(tree)
        node = tree.nodes.new(self.kind)
        node.location = _place_new_node(tree, target)
        attach(tree, node, target)
        return {"FINISHED"}


class CTX_OT_select_section(bpy.types.Operator):
    bl_idname = "ctx.select_section"
    bl_label = "Select Section"
    bl_description = "Make this the active section node and select its objects"
    bl_options = {"REGISTER", "UNDO"}

    section_id: StringProperty()

    def execute(self, context):
        tree = T.get_tree(create=False)
        if tree is None:
            return {"CANCELLED"}
        for n in tree.nodes:
            n.select = n.bl_idname == "CTX_SectionNode" and n.section_id == self.section_id
            if n.select:
                tree.nodes.active = n
        coll = sm.find_section_collection(self.section_id)
        if coll is not None:
            for o in context.view_layer.objects:
                o.select_set(False)
            for o in sm.owned_objects(coll):
                if o.name in context.view_layer.objects:
                    o.select_set(True)
        return {"FINISHED"}


class CTX_OT_jump_to_node(bpy.types.Operator):
    bl_idname = "ctx.jump_to_node"
    bl_label = "Jump to Node"
    bl_description = "Show the active object's Section node in the Context Editor"

    def execute(self, context):
        obj = context.active_object
        coll = sm.section_of_object(obj) if obj else None
        tree = T.get_tree(create=False)
        if coll is None or tree is None:
            self.report({"WARNING"}, "The active object is not in a section")
            return {"CANCELLED"}
        node = T.section_node_for(tree, coll)
        for n in tree.nodes:
            n.select = n == node
        tree.nodes.active = node
        area, space = _context_space(context)
        if area is None:
            if WORKSPACE_NAME in bpy.data.workspaces:
                context.window.workspace = bpy.data.workspaces[WORKSPACE_NAME]
            self.report({"INFO"}, "Selected %s in the Context Editor" % node.draw_label())
            return {"FINISHED"}
        region = next(r for r in area.regions if r.type == "WINDOW")
        with context.temp_override(area=area, region=region, space_data=space):
            bpy.ops.node.view_selected()
        return {"FINISHED"}


class CTX_OT_export(bpy.types.Operator):
    bl_idname = "ctx.export"
    bl_label = "Export Context"
    bl_description = "Write a run folder: context.json, base.blend snapshot, refs and block-out previews"

    def execute(self, context):
        try:
            run_dir, ctx, proc = export.export_run(context.scene)
        except Exception as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        context.scene.ctx_last_run = run_dir
        msg = "Exported %d sections to %s" % (len(ctx["sections"]), run_dir)
        if proc is not None:
            msg += " (block-out previews rendering in the background)"
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class CTX_OT_palette_add(bpy.types.Operator):
    bl_idname = "ctx.palette_add"
    bl_label = "Add Palette Color"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        node = getattr(context, "node", None) or T.project_node(T.get_tree())
        node.palette.add()
        return {"FINISHED"}


class CTX_OT_palette_remove(bpy.types.Operator):
    bl_idname = "ctx.palette_remove"
    bl_label = "Remove Palette Color"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        node = getattr(context, "node", None) or T.project_node(T.get_tree())
        if len(node.palette):
            node.palette.remove(len(node.palette) - 1)
        return {"FINISHED"}


# ---------------------------------------------------------------- panels

def _draw_sections(layout, tree):
    nodes = sorted(T.section_nodes(tree), key=lambda n: (n.order, n.draw_label()))
    if not nodes:
        layout.label(text="No sections yet")
        return
    col = layout.column(align=True)
    for n in nodes:
        row = col.row(align=True)
        icon = {"draft": "RADIOBUT_OFF", "ready": "RADIOBUT_ON", "locked": "LOCKED"}[n.status]
        op = row.operator("ctx.select_section", text="%d · %s" % (n.order, n.draw_label()), icon=icon,
                          depress=(tree.nodes.active == n))
        op.section_id = n.section_id
        row.prop(n, "status", text="")


class CTX_PT_node_context(bpy.types.Panel):
    bl_space_type = "NODE_EDITOR"
    bl_region_type = "UI"
    bl_category = "Context"
    bl_label = "Context"

    @classmethod
    def poll(cls, context):
        return context.space_data.tree_type == T.TREE_ID

    def draw(self, context):
        layout = self.layout
        layout.operator("ctx.make_section", icon="OUTLINER_COLLECTION")
        tree = T.get_tree(create=False)
        if tree is None:
            return
        layout.label(text="Sections")
        _draw_sections(layout, tree)
        sec = selected_section(context)
        layout.label(text="Attach to %s" % (sec.draw_label() if sec else "Project"))
        row = layout.row(align=True)
        for idname, label, _ in ADD_KINDS:
            row.operator("ctx.add_context", text=label).kind = idname
        layout.separator()
        layout.prop(context.scene, "ctx_runs_dir", text="Runs")
        layout.operator("ctx.export", icon="EXPORT")


class CTX_PT_view3d_context(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Context"
    bl_label = "Context"

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        coll = sm.section_of_object(obj) if obj else None
        tree = T.get_tree(create=False)
        node = T.section_node_for(tree, coll) if (tree and coll) else None
        if node is not None:
            box = layout.box()
            box.label(text=node.draw_label(), icon="OUTLINER_COLLECTION")
            box.label(text="Status: %s · order %d" % (node.status, node.order))
            if node.intent:
                col = box.column(align=True)
                col.scale_y = 0.8
                for ln in [l for l in node.intent.as_string().splitlines() if l.strip()][:6]:
                    col.label(text=ln[:70])
            for n in T.linked_context_nodes(node):
                if n.bl_idname == "CTX_ReferenceImageNode":
                    box.label(text=n.image.name if n.image else "?", icon="IMAGE_DATA")
                elif n.bl_idname == "CTX_NoteNode":
                    box.label(text=n.draw_label(), icon="TEXT")
                elif n.bl_idname == "CTX_LinkNode":
                    box.label(text=n.label or n.url, icon="URL")
                elif n.bl_idname == "CTX_GreasePencilNode":
                    box.label(text=n.draw_label(), icon="OUTLINER_OB_GREASEPENCIL")
        elif obj is not None:
            layout.label(text="Active object is not in a section")
        layout.operator("ctx.make_section", icon="OUTLINER_COLLECTION")
        layout.operator("ctx.jump_to_node", icon="NODETREE")
        layout.operator("ctx.setup_workspace", icon="WORKSPACE")
        layout.operator("ctx.export", icon="EXPORT")


CLASSES = (
    CTX_OT_setup_workspace,
    CTX_OT_make_section,
    CTX_OT_add_context,
    CTX_OT_select_section,
    CTX_OT_jump_to_node,
    CTX_OT_export,
    CTX_OT_palette_add,
    CTX_OT_palette_remove,
    CTX_PT_node_context,
    CTX_PT_view3d_context,
)


def register():
    bpy.types.Scene.ctx_runs_dir = StringProperty(
        name="Runs folder", subtype="DIR_PATH", default="//runs",
        description="Where Export Context writes run folders",
    )
    bpy.types.Scene.ctx_last_run = StringProperty(name="Last run", subtype="DIR_PATH")
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
    del bpy.types.Scene.ctx_last_run
    del bpy.types.Scene.ctx_runs_dir
