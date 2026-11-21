"""Context Editor node tree, socket and node types."""

import bpy
from bpy.props import (
    CollectionProperty,
    EnumProperty,
    FloatVectorProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)

from . import scene_model as sm

TREE_ID = "CTX_ContextTree"
SOCKET_ID = "CTX_SocketContext"

STATUS_ITEMS = [
    ("draft", "Draft", "Not ready for the pipeline"),
    ("ready", "Ready", "The lead will plan a task for it"),
    ("locked", "Locked", "Accepted; the pipeline leaves it alone"),
]
STATUS_COLORS = {
    "draft": (0.32, 0.32, 0.34),
    "ready": (0.20, 0.42, 0.28),
    "locked": (0.22, 0.30, 0.48),
}

# Images and texts on the board get a fake user, so a save never drops them, even after their node
# is deleted or emptied. (The "shield" button in the ID template.)
KEPT_PROPS = ("image", "text_block", "intent", "style_notes")


def _keep(idb):
    if idb is not None and idb.library is None and not idb.use_fake_user:
        idb.use_fake_user = True


def _keep_update(attr):
    def update(self, context):
        _keep(getattr(self, attr))
    return update


def keep_board():
    """Fake users for every context board and every image/text it points at."""
    for tree in bpy.data.node_groups:
        if tree.bl_idname != TREE_ID:
            continue
        _keep(tree)
        for n in tree.nodes:
            for attr in KEPT_PROPS:
                _keep(getattr(n, attr, None))


@bpy.app.handlers.persistent
def _keep_on_load(_dummy=None):
    keep_board()


def _keep_after_register():
    try:
        keep_board()
    except Exception:  # bpy.data can still be restricted right after startup
        return 0.5
    return None


class ContextTree(bpy.types.NodeTree):
    """Creative context for scene sections"""

    bl_idname = TREE_ID
    bl_label = "Context Editor"
    bl_icon = "OUTLINER_COLLECTION"


class ContextSocket(bpy.types.NodeSocket):
    bl_idname = SOCKET_ID
    bl_label = "Context"

    def draw(self, context, layout, node, text):
        layout.label(text=text)

    @classmethod
    def draw_color_simple(cls):
        return (0.93, 0.66, 0.25, 1.0)


class ContextNode:
    @classmethod
    def poll(cls, ntree):
        return ntree.bl_idname == TREE_ID


# ---------------------------------------------------------------- Project

class CTX_PaletteColor(bpy.types.PropertyGroup):
    color: FloatVectorProperty(subtype="COLOR_GAMMA", size=3, min=0.0, max=1.0, default=(0.5, 0.5, 0.5))


class ProjectNode(ContextNode, bpy.types.Node):
    """Project-wide context. Anything linked in applies to every section."""

    bl_idname = "CTX_ProjectNode"
    bl_label = "Project"
    bl_icon = "WORLD"
    bl_width_default = 260

    style_notes: PointerProperty(type=bpy.types.Text, name="Style notes", update=_keep_update("style_notes"))
    era: StringProperty(name="Era")
    scale_unit: StringProperty(name="Scale unit", default="m")
    palette: CollectionProperty(type=CTX_PaletteColor)

    def init(self, context):
        self.inputs.new(SOCKET_ID, "Context", use_multi_input=True)
        self.use_custom_color = True
        self.color = (0.40, 0.30, 0.18)

    def draw_buttons(self, context, layout):
        layout.prop(self, "era")
        layout.prop(self, "scale_unit")
        layout.template_ID(self, "style_notes", new="text.new", open="text.open")
        row = layout.row(align=True)
        row.label(text="Palette")
        row.context_pointer_set("node", self)
        row.operator("ctx.palette_add", text="", icon="ADD")
        row.operator("ctx.palette_remove", text="", icon="REMOVE")
        if self.palette:
            grid = layout.grid_flow(columns=6, align=True)
            for item in self.palette:
                grid.prop(item, "color", text="")


# ---------------------------------------------------------------- Section

def _on_section_collection(self, context):
    coll = self.collection
    if coll is None:
        return
    self.section_id = sm.ensure_section_id(coll)
    if not self.title:
        self.title = coll.name.replace("_", " ").title()


def _on_status(self, context):
    self.color = STATUS_COLORS.get(self.status, STATUS_COLORS["draft"])


class SectionNode(ContextNode, bpy.types.Node):
    """A scene collection the pipeline builds as one task"""

    bl_idname = "CTX_SectionNode"
    bl_label = "Section"
    bl_icon = "OUTLINER_COLLECTION"
    bl_width_default = 280

    collection: PointerProperty(type=bpy.types.Collection, name="Collection", update=_on_section_collection)
    section_id: StringProperty(name="Section ID")
    title: StringProperty(name="Title")
    intent: PointerProperty(type=bpy.types.Text, name="Intent", update=_keep_update("intent"))
    status: EnumProperty(items=STATUS_ITEMS, name="Status", default="draft", update=_on_status)
    order: IntProperty(name="Order", default=0, min=0)

    def init(self, context):
        self.inputs.new(SOCKET_ID, "Context", use_multi_input=True)
        self.use_custom_color = True
        self.color = STATUS_COLORS["draft"]

    def draw_label(self):
        return self.title or (self.collection.name if self.collection else "Section")

    def draw_buttons(self, context, layout):
        layout.prop(self, "collection", text="")
        if self.collection:
            n = len(sm.owned_objects(self.collection))
            layout.label(text="%s · %d objects" % (self.collection.name, n), icon="OUTLINER_COLLECTION")
        layout.prop(self, "title")
        row = layout.row(align=True)
        row.prop(self, "status", text="")
        row.prop(self, "order")
        layout.template_ID(self, "intent", new="text.new", open="text.open")
        if self.intent:
            lines = [ln for ln in self.intent.as_string().splitlines() if ln.strip()]
            col = layout.column(align=True)
            col.scale_y = 0.8
            for ln in lines[:4]:
                col.label(text=ln[:60])


# ---------------------------------------------------------------- Context nodes

class ReferenceImageNode(ContextNode, bpy.types.Node):
    """A reference image"""

    bl_idname = "CTX_ReferenceImageNode"
    bl_label = "Reference Image"
    bl_icon = "IMAGE_DATA"
    bl_width_default = 240

    image: PointerProperty(type=bpy.types.Image, name="Image", update=_keep_update("image"))
    thumb_scale: IntProperty(name="Thumbnail size", default=8, min=3, max=20)

    def init(self, context):
        self.outputs.new(SOCKET_ID, "Context")

    def draw_label(self):
        return self.image.name if self.image else "Reference Image"

    def draw_buttons(self, context, layout):
        layout.template_ID(self, "image", open="image.open")
        if self.image:
            self.image.preview_ensure()
            if self.image.preview:
                layout.template_icon(icon_value=self.image.preview.icon_id, scale=self.thumb_scale)

    def draw_buttons_ext(self, context, layout):
        self.draw_buttons(context, layout)
        layout.prop(self, "thumb_scale")


class NoteNode(ContextNode, bpy.types.Node):
    """A note: a Text datablock, written in the Text Editor"""

    bl_idname = "CTX_NoteNode"
    bl_label = "Note"
    bl_icon = "TEXT"
    bl_width_default = 240

    text_block: PointerProperty(type=bpy.types.Text, name="Text", update=_keep_update("text_block"))

    def init(self, context):
        self.outputs.new(SOCKET_ID, "Context")

    def draw_label(self):
        return self.text_block.name if self.text_block else "Note"

    def draw_buttons(self, context, layout):
        layout.template_ID(self, "text_block", new="text.new", open="text.open")

    def full_text(self):
        return self.text_block.as_string().strip() if self.text_block else ""


class LinkNode(ContextNode, bpy.types.Node):
    """A web link"""

    bl_idname = "CTX_LinkNode"
    bl_label = "Link"
    bl_icon = "URL"
    bl_width_default = 240

    url: StringProperty(name="URL")
    label: StringProperty(name="Label")

    def init(self, context):
        self.outputs.new(SOCKET_ID, "Context")

    def draw_label(self):
        return self.label or "Link"

    def draw_buttons(self, context, layout):
        layout.prop(self, "label", text="Label")
        row = layout.row(align=True)
        row.prop(self, "url", text="URL")
        sub = row.row(align=True)
        sub.enabled = bool(self.url)
        op = sub.operator("wm.url_open", text="", icon="URL")
        op.url = self.url


def _is_grease_pencil(self, obj):
    return obj.type == "GREASEPENCIL"


class GreasePencilNode(ContextNode, bpy.types.Node):
    """A Grease Pencil object: exported as a render and as its stroke points"""

    bl_idname = "CTX_GreasePencilNode"
    bl_label = "Grease Pencil"
    bl_icon = "OUTLINER_OB_GREASEPENCIL"
    bl_width_default = 240

    object: PointerProperty(type=bpy.types.Object, name="Object", poll=_is_grease_pencil)

    def init(self, context):
        self.outputs.new(SOCKET_ID, "Context")

    def draw_label(self):
        return self.object.name if self.object else "Grease Pencil"

    def draw_buttons(self, context, layout):
        layout.prop(self, "object", text="")


NODE_CLASSES = (ProjectNode, SectionNode, ReferenceImageNode, NoteNode, LinkNode, GreasePencilNode)
CONTEXT_NODE_IDS = {"CTX_ReferenceImageNode", "CTX_NoteNode", "CTX_LinkNode", "CTX_GreasePencilNode"}


# ---------------------------------------------------------------- helpers

def get_tree(create=True):
    for ng in bpy.data.node_groups:
        if ng.bl_idname == TREE_ID:
            return ng
    if not create:
        return None
    tree = bpy.data.node_groups.new("Context", TREE_ID)
    tree.use_fake_user = True
    proj = tree.nodes.new("CTX_ProjectNode")
    proj.location = (-600, 300)
    return tree


def project_node(tree):
    for n in tree.nodes:
        if n.bl_idname == "CTX_ProjectNode":
            return n
    return None


def section_nodes(tree):
    return [n for n in tree.nodes if n.bl_idname == "CTX_SectionNode"]


def section_node_for(tree, coll):
    for n in section_nodes(tree):
        if n.collection == coll:
            return n
    return None


def linked_context_nodes(node):
    """Context nodes linked into ``node``'s Context input, following reroutes."""
    out = []
    if not node.inputs:
        return out
    stack = [lk.from_node for lk in node.inputs[0].links if lk.is_valid and not lk.is_muted]
    while stack:
        n = stack.pop()
        if n.bl_idname == "NodeReroute":
            stack.extend(lk.from_node for lk in n.inputs[0].links)
        elif n.bl_idname in CONTEXT_NODE_IDS and not n.mute:
            out.append(n)
    out.sort(key=lambda n: (n.location.y * -1, n.location.x))
    return out


# ---------------------------------------------------------------- add menu

def _add_menu(self, context):
    if context.space_data.tree_type != TREE_ID:
        return
    layout = self.layout
    for cls in NODE_CLASSES:
        op = layout.operator("node.add_node", text=cls.bl_label, icon=cls.bl_icon)
        op.type = cls.bl_idname
        op.use_transform = True


CLASSES = (CTX_PaletteColor, ContextTree, ContextSocket) + NODE_CLASSES


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.NODE_MT_add.append(_add_menu)
    bpy.app.handlers.load_post.append(_keep_on_load)
    bpy.app.timers.register(_keep_after_register, first_interval=0.1)


def unregister():
    if _keep_on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_keep_on_load)
    bpy.types.NODE_MT_add.remove(_add_menu)
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
