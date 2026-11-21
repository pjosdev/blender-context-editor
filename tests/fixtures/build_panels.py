# Generic test build: a beveled plate on top of each block-out object, one material.
import bmesh
import ctx_runtime as ctx

sec = ctx.section()
sec.clean()
mat = sec.material("paint", base_color=(0.7, 0.66, 0.55), roughness=0.6)
for i, b in enumerate(sorted(sec.blockout, key=lambda o: o.name)):
    lo, hi = sec.bbox([b])
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    sx, sy = (hi[0] - lo[0]) * 0.6, (hi[1] - lo[1]) * 0.6
    bmesh.ops.scale(bm, vec=(sx, sy, 0.04), verts=bm.verts)
    o = sec.mesh_object("plate_%d" % i, bm=bm,
                        location=((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, hi[2] + 0.02 + sec.rng.random() * 0.01))
    sec.assign(o, mat)
    sec.modifier(o, "bevel", "BEVEL").width = 0.01
