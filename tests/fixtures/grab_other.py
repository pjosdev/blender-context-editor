# Deliberately conflicting: names its datablock with ANOTHER section's prefix via env CTX_OTHER_PREFIX.
import os
import bpy
import ctx_runtime as ctx
sec = ctx.section()
sec.clean()
other = os.environ["CTX_OTHER_PREFIX"]
mat = bpy.data.materials.get(other + "paint") or bpy.data.materials.new(other + "paint")
mat.diffuse_color = (1, 0, 0, 1)
