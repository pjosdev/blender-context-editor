"""Drag and drop image files onto the Context Editor -> Reference Image nodes."""

import os

import bpy
from bpy.props import CollectionProperty, StringProperty

from . import tree as T
from . import ui

IMAGE_EXTS = ".png;.jpg;.jpeg;.webp;.tif;.tiff;.bmp;.exr;.hdr;.tga"


class CTX_OT_drop_images(bpy.types.Operator):
    bl_idname = "ctx.drop_images"
    bl_label = "Add Reference Images"
    bl_description = "Create Reference Image nodes from image files"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    directory: StringProperty(subtype="DIR_PATH", options={"SKIP_SAVE", "HIDDEN"})
    files: CollectionProperty(type=bpy.types.OperatorFileListElement, options={"SKIP_SAVE", "HIDDEN"})
    filepath: StringProperty(subtype="FILE_PATH", options={"SKIP_SAVE", "HIDDEN"})

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == "NODE_EDITOR"

    def _paths(self):
        if self.files and self.directory:
            return [os.path.join(self.directory, f.name) for f in self.files if f.name]
        if self.filepath:
            return [self.filepath]
        return []

    def execute(self, context):
        tree = T.get_tree()
        target = ui.selected_section(context)
        added = 0
        for path in self._paths():
            if os.path.splitext(path)[1].lower() not in IMAGE_EXTS.split(";"):
                continue
            img = bpy.data.images.load(path, check_existing=True)
            node = tree.nodes.new("CTX_ReferenceImageNode")
            node.location = ui._place_new_node(tree, target)
            node.image = img
            ui.attach(tree, node, target)
            added += 1
        if not added:
            self.report({"WARNING"}, "No image files")
            return {"CANCELLED"}
        self.report({"INFO"}, "Added %d reference image(s)%s" % (
            added, " to " + target.draw_label() if target else ""))
        return {"FINISHED"}

    def invoke(self, context, event):
        if self.directory or self.filepath:
            return self.execute(context)
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


class CTX_FH_reference_images(bpy.types.FileHandler):
    bl_idname = "CTX_FH_reference_images"
    bl_label = "Context reference images"
    bl_import_operator = "ctx.drop_images"
    bl_file_extensions = IMAGE_EXTS

    @classmethod
    def poll_drop(cls, context):
        space = context.space_data
        return space is not None and space.type == "NODE_EDITOR" and space.tree_type == T.TREE_ID


CLASSES = (CTX_OT_drop_images, CTX_FH_reference_images)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
