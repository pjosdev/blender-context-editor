"""Helpers every build script imports.

    import ctx_runtime as ctx
    sec = ctx.section()          # the section this script builds (set by the runner)
    sec.clean()                  # remove everything this section built before
    ...build with sec.mesh_object / sec.material / sec.modifier ...

Rules (checked by run_script.py's datablock diff, not by trust):
- Touch only what the section owns: its collection, untagged sub-collections,
  their objects, and data used only by those objects.
- Every new datablock is named with sec.prefix (ctx_<id6>_). The helpers do it.
- Deterministic: use sec.rng, never the global random module. No network.
- Never touch the world, scene settings, or anything in another section.
"""

import os
import random
import sys

import bpy

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))
import scene_model as sm  # noqa: E402

_current = {"id": os.environ.get("CTX_SECTION_ID")}


def set_section(section_id):
    _current["id"] = section_id


def section(section_id=None):
    sid = section_id or _current["id"]
    if not sid:
        raise RuntimeError("No section id. Run through tools/run_script.py or call ctx_runtime.set_section().")
    return Section(sid)


class Section:
    def __init__(self, section_id):
        self.id = section_id
        self.collection = sm.find_section_collection(section_id)
        if self.collection is None:
            raise RuntimeError("No collection has ctx_section_id=%s" % section_id)
        self.prefix = sm.prefix_for(section_id)
        self.rng = random.Random(int(section_id[:8], 16))

    # ------------------------------------------------------------ queries

    def name(self, n):
        return n if n.startswith(self.prefix) else self.prefix + n

    @property
    def objects(self):
        """Objects owned by the section, block-out and built."""
        return sm.owned_objects(self.collection)

    @property
    def blockout(self):
        """The artist's block-out objects (owned, not built by this section).

        Grease Pencil objects are the artist's drawings, not block-out geometry."""
        return [o for o in self.objects if not o.name.startswith(self.prefix) and o.type != "GREASEPENCIL"]

    def bbox(self, objects=None):
        """((min x, y, z), (max x, y, z)) of the block-out, world space."""
        return sm.world_bbox(objects if objects is not None else self.blockout)

    # ------------------------------------------------------------ cleanup

    def clean(self):
        """Remove everything this section built before, so reruns are idempotent."""
        p = self.prefix
        for o in list(bpy.data.objects):
            if o.name.startswith(p):
                bpy.data.objects.remove(o, do_unlink=True)
        for o in self.blockout:
            for m in list(o.modifiers):
                if m.name.startswith(p):
                    o.modifiers.remove(m)
            for c in list(o.constraints):
                if c.name.startswith(p):
                    o.constraints.remove(c)
        for c in list(bpy.data.collections):
            if c.name.startswith(p):
                bpy.data.collections.remove(c)
        # Prefixed data still used by block-out objects (a copied mesh, an assigned
        # material) stays; the helpers reuse it by name, so reruns converge.
        for _ in range(3):
            for kind in ("meshes", "curves", "lights", "cameras", "materials", "node_groups",
                         "images", "textures", "fonts"):
                dc = getattr(bpy.data, kind)
                for idb in list(dc):
                    if idb.name.startswith(p) and idb.users - int(idb.use_fake_user) == 0:
                        dc.remove(idb)

    # ------------------------------------------------------------ building

    def sub_collection(self, n):
        name = self.name(n)
        c = bpy.data.collections.get(name)
        if c is None:
            c = bpy.data.collections.new(name)
            self.collection.children.link(c)
        return c

    def link(self, obj, collection=None):
        target = collection or self.collection
        if obj.name not in target.objects:
            target.objects.link(obj)
        return obj

    def mesh_object(self, n, verts=(), faces=(), edges=(), location=(0, 0, 0), collection=None, bm=None):
        """New mesh object from verts/faces, or from a bmesh (bm is freed)."""
        name = self.name(n)
        me = bpy.data.meshes.new(name)
        if bm is not None:
            bm.to_mesh(me)
            bm.free()
        else:
            me.from_pydata(list(verts), list(edges), list(faces))
        me.update()
        obj = bpy.data.objects.new(name, me)
        obj.location = location
        return self.link(obj, collection)

    def object(self, n, data=None, collection=None):
        """New object of any kind (pass prefixed data, e.g. from sec.light)."""
        obj = bpy.data.objects.new(self.name(n), data)
        return self.link(obj, collection)

    def light(self, n, kind="POINT", energy=100.0, color=(1, 1, 1), location=(0, 0, 0), collection=None):
        ld = bpy.data.lights.new(self.name(n), kind)
        ld.energy = energy
        ld.color = color
        obj = bpy.data.objects.new(self.name(n), ld)
        obj.location = location
        return self.link(obj, collection)

    def duplicate(self, src, n, collection=None, linked_data=False):
        """Copy an object (and its data unless linked_data) under a prefixed name."""
        obj = src.copy()
        obj.name = self.name(n)
        if src.data is not None and not linked_data:
            obj.data = src.data.copy()
            obj.data.name = self.name(n)
        for c in list(obj.users_collection):
            c.objects.unlink(obj)
        return self.link(obj, collection)

    def material(self, n, base_color=(0.8, 0.8, 0.8), roughness=0.5, metallic=0.0, emission=None,
                 emission_strength=0.0):
        """Principled BSDF material (reused if it already exists this run)."""
        name = self.name(n)
        mat = bpy.data.materials.get(name)
        if mat is None:
            mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = tuple(base_color[:3]) + (1.0,)
            bsdf.inputs["Roughness"].default_value = roughness
            bsdf.inputs["Metallic"].default_value = metallic
            if emission is not None:
                bsdf.inputs["Emission Color"].default_value = tuple(emission[:3]) + (1.0,)
                bsdf.inputs["Emission Strength"].default_value = emission_strength
        mat.diffuse_color = tuple(base_color[:3]) + (1.0,)
        return mat

    def node_group(self, n, tree_type="ShaderNodeTree"):
        name = self.name(n)
        ng = bpy.data.node_groups.get(name)
        if ng is None:
            ng = bpy.data.node_groups.new(name, tree_type)
        return ng

    def assign(self, obj, mat, slot=None):
        """Put a material on an object. Block-out data shared outside the section is copied first."""
        if obj.data is not None and obj.data.users > 1:
            users = [o for o in bpy.data.objects if o.data == obj.data]
            if any(o not in self.objects for o in users):
                obj.data = obj.data.copy()
                obj.data.name = self.name(obj.name)
        if slot is None:
            obj.data.materials.clear()
            obj.data.materials.append(mat)
        else:
            while len(obj.data.materials) <= slot:
                obj.data.materials.append(None)
            obj.data.materials[slot] = mat
        return mat

    def modifier(self, obj, n, kind):
        name = self.name(n)
        m = obj.modifiers.get(name)
        if m is None:
            m = obj.modifiers.new(name, kind)
        return m
