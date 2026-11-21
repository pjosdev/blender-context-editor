---
name: setup
description: Check that this agent can reach Blender, that the Context Editor add-on is installed and current, and that the agent's skills match it; installs or updates what's missing. Use before the first plan, or when another skill says Blender or the add-on isn't ready.
---

Invoking this skill is the go-ahead to install or update the add-on and the skills.

1. **Blender connection.** Over the Blender MCP server, `execute_blender_code`:
   `import bpy; result = {"blender": bpy.app.version_string, "file": bpy.data.filepath}`.
   If there are no Blender MCP tools or it can't connect, stop: tell the artist to install a Blender MCP
   add-on in Blender, enable it, start its server, and connect it to this agent. Nothing else works
   without it.
2. **The add-on.** Over the MCP:
   ```python
   import os, sys, ast, addon_utils
   m = sys.modules.get("context_editor")
   result = {"enabled": addon_utils.check("context_editor")[1], "python": sys.executable}
   if m:
       d = os.path.dirname(m.__file__)
       src = open(os.path.join(d, "__init__.py"), encoding="utf-8").read()
       result.update(addon=d, running=list(m.bl_info["version"]),
                     installed=list(ast.literal_eval(src[src.index("{"):src.index("}") + 1])["version"]))
   ```
   - **Enabled, `running` = `installed`:** go to step 4.
   - **`running` ≠ `installed`:** a newer version is installed but Blender still runs the old one. Tell the
     artist to save their work and restart Blender, then run this skill again.
   - **Not there:** step 3.
3. **Install the add-on.** If the folder two levels above this skill holds `tools/build_addon.py` (the
   Claude plugin, or a copy of the repo's `addon/`), build and install it from there over the MCP, with
   that folder as `<src>` (forward slashes):
   ```python
   import runpy, tempfile, bpy, addon_utils
   zip_path = runpy.run_path("<src>/tools/build_addon.py")["build"](tempfile.mkdtemp())
   bpy.ops.preferences.addon_install(filepath=zip_path, overwrite=True)
   addon_utils.enable("context_editor", default_set=True)
   bpy.ops.wm.save_userpref()
   result = zip_path
   ```
   If it replaced an older version, the artist must restart Blender (step 2). Otherwise ask the artist to
   install `context_editor.zip` themselves (Edit > Preferences > Add-ons > Install from Disk) and stop.
4. **The skills.** If this skill's own text has a line `installed by the Context Editor add-on, version X`
   and X isn't `installed` from step 2, or the artist asks, refresh them over the MCP:
   `import context_editor.agent_skills as s; result = s.install(["agents"])` (`["claude"]` for Claude
   Code without the plugin; both if they use both; `s.install(["custom"], root="<folder>")` for a
   folder the artist names). Tell the artist to start a new agent session so it
   loads them. A plugin install has no version line; skip this step.
5. Report what you found and changed in a few lines. Then how to start: 3D View sidebar > Context >
   **Make Section from Active Collection**, set sections to **Ready**, attach references and notes, save
   the file, then ask for the plan skill. Stop there; don't start it yourself.
