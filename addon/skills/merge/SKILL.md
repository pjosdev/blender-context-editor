---
name: merge
description: Merge the sections the artist kept into build.blend. Use once the artist has said keep for the sections they want.
argument-hint: "[run folder]"
---

`<addon>` is the Context Editor add-on's folder in Blender and `<python>` is Blender's own Python. Take
both from the run's `context.json` (`addon_dir`, `python_bin`). With no run yet, ask Blender over the
Blender MCP server (`execute_blender_code`):
`import os, sys, context_editor; result = {"addon": os.path.dirname(context_editor.__file__), "python": sys.executable}`.
If that fails, use the setup skill. Read `<addon>/PIPELINE.md` first.

Run folder: `$ARGUMENTS` (empty = newest).

1. `"<python>" <addon>/tools/decide.py <run>`. If no section is kept, ask the artist which to keep and
   record it (PIPELINE.md "Keep / redo").
2. `"<python>" <addon>/tools/merge.py <run>`. It runs the kept scripts in order on a fresh `base.blend`,
   stops on any conflict or ownership violation, and otherwise writes `build.blend` and
   `previews/build.png`.
3. If it stopped, relay the CONFLICT / VIOLATION lines as they are and name the scripts involved. Don't
   edit scripts to force it through; that's a redo, the artist's call.
4. If it passed, look at `previews/build.png`, mention any visible seam problems in one line, and tell
   the artist: open `build.blend`, or use the `apply` skill to put it onto their own file (with a backup).
   Then **stop**; apply only when they ask.
