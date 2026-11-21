"""Inside Blender. `-- <zip>`: install the add-on, build a board, save board.blend.
`-- --check`: enable the installed add-on and assert the board in the opened file is intact."""

import os
import sys

import addon_utils
import bpy

args = sys.argv[sys.argv.index("--") + 1:]
TMP = os.environ["CTX_TMP"]

if args[0] != "--check":
    bpy.ops.preferences.addon_install(filepath=args[0], overwrite=True)
    addon_utils.enable("context_editor", default_set=True)
    bpy.ops.wm.save_userpref()
    from context_editor import tree as T

    assert "CTX_ContextTree" in [c.bl_idname for c in bpy.types.NodeTree.__subclasses__()]
    c = bpy.data.collections.new("PART")
    bpy.context.scene.collection.children.link(c)
    import bmesh
    me = bpy.data.meshes.new("part_box")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(me)
    bm.free()
    c.objects.link(bpy.data.objects.new("part_box", me))
    bpy.ops.ctx.make_section(collection="PART")
    t = T.get_tree()
    sec = T.section_node_for(t, c)
    sec.intent = bpy.data.texts.new("intent")
    sec.intent.write("Intent text")
    sec.status = "ready"
    t.nodes.active = sec
    for kind in ("CTX_ReferenceImageNode", "CTX_NoteNode", "CTX_LinkNode"):
        bpy.ops.ctx.add_context(kind=kind)
    img = bpy.data.images.new("ref", 32, 32)
    img.pack()
    for n in t.nodes:
        if n.bl_idname == "CTX_ReferenceImageNode":
            n.image = img
        elif n.bl_idname == "CTX_NoteNode":
            n.text_block = bpy.data.texts.new("note")
            n.text_block.write("note text")
        elif n.bl_idname == "CTX_LinkNode":
            n.url, n.label = "https://example.com", "lbl"
    T.project_node(t).palette.add()
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(TMP, "board.blend"))
    print("CTX_ROUNDTRIP_SAVED")

    # What the setup skill asks over the MCP (step 2), then the skills button and a snapshot,
    # all from the installed copy of the add-on.
    import ast, json, runpy
    m = sys.modules.get("context_editor")
    d = os.path.dirname(m.__file__)
    src = open(os.path.join(d, "__init__.py"), encoding="utf-8").read()
    installed = list(ast.literal_eval(src[src.index("{"):src.index("}") + 1])["version"])
    assert addon_utils.check("context_editor")[1] and list(m.bl_info["version"]) == installed
    for rel in ("PIPELINE.md", "tools/run_script.py", "tools/snapshot_live.py", "skills/plan/SKILL.md",
                "skills/build-section/SKILL.md"):
        assert os.path.isfile(os.path.join(d, rel)), rel
    assert not os.path.exists(os.path.join(d, "agents")) and not os.path.exists(os.path.join(d, ".claude-plugin"))
    import context_editor.agent_skills as s
    r = s.install(["agents"], root=os.path.join(TMP, "skills"))
    assert len(r["written"]) == 7 and not r["skipped"], r
    assert s.installed_version("agents", root=os.path.join(TMP, "skills")) == ".".join(map(str, installed))
    prefs = bpy.context.preferences.addons["context_editor"].preferences   # the button, custom folder only
    prefs.skills_agents = prefs.skills_claude = False
    os.makedirs(os.path.join(TMP, "custom_skills"))
    prefs.skills_custom, prefs.skills_custom_dir = True, os.path.join(TMP, "custom_skills")
    assert bpy.ops.ctx.install_skills() == {"FINISHED"}
    assert s.installed_version("custom", root=os.path.join(TMP, "custom_skills")) == ".".join(map(str, installed))
    # Default folder missing (the test's home is empty): "use another folder", then "create it".
    ver = ".".join(map(str, installed))
    assert not os.path.isdir(s._target("agents")), s._target("agents")
    prefs.skills_custom, prefs.skills_agents = False, True
    pick = os.path.join(TMP, "picked")
    os.makedirs(pick)
    assert bpy.ops.ctx.install_skills("EXEC_DEFAULT", missing_choice="CUSTOM", folder=pick) == {"FINISHED"}
    assert s.installed_version("custom", root=pick) == ver and not os.path.isdir(s._target("agents"))
    assert bpy.ops.ctx.install_skills("EXEC_DEFAULT", missing_choice="CREATE") == {"FINISHED"}
    assert s.installed_version("agents") == ver
    assert s._status("agents", None).endswith("(skills %s)" % ver), s._status("agents", None)
    snap = runpy.run_path(os.path.join(d, "tools", "snapshot_live.py"), run_name="ctx_snapshot")["snapshot"](TMP)
    assert "error" not in snap, snap
    ctx = json.load(open(os.path.join(snap["run_dir"], "context.json"), encoding="utf-8"))
    assert os.path.normcase(ctx["addon_dir"]) == os.path.normcase(d) and os.path.isfile(ctx["python_bin"]), ctx
    print("CTX_SNAPSHOT", json.dumps({"run_dir": snap["run_dir"], "python": ctx["python_bin"], "addon": d}))
else:
    addon_utils.enable("context_editor")
    from context_editor import tree as T

    t = T.get_tree(create=False)
    assert t is not None and t.bl_idname == "CTX_ContextTree", t
    sec = [n for n in t.nodes if n.bl_idname == "CTX_SectionNode"][0]
    assert sec.collection and sec.collection.name == "PART"
    assert sec.section_id and sec.collection["ctx_section_id"] == sec.section_id
    assert sec.intent.as_string() == "Intent text" and sec.status == "ready"
    linked = {n.bl_idname: n for n in T.linked_context_nodes(sec)}
    assert set(linked) == {"CTX_ReferenceImageNode", "CTX_NoteNode", "CTX_LinkNode"}, linked
    im = linked["CTX_ReferenceImageNode"].image
    assert im is not None and im.name == "ref", im
    assert im.packed_file is not None or im.source == "GENERATED", (im.source, im.packed_file)
    assert linked["CTX_NoteNode"].full_text() == "note text"
    assert linked["CTX_LinkNode"].url == "https://example.com"
    assert len(T.project_node(t).palette) == 1
    print("CTX_ROUNDTRIP_OK")
