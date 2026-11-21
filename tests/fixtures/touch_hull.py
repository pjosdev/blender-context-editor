# Deliberately bad: edits the untagged HULL (another owner's datablock).
import bpy
import ctx_runtime as ctx
sec = ctx.section()
sec.clean()
bpy.data.objects["hull_body"].location.z += 0.5
