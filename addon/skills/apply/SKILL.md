---
name: apply
description: Back up the artist's own .blend, then apply the kept sections to it, either to the closed file or live in the open Blender. Use after merge, when the artist wants the result in their file.
argument-hint: "[run folder] [live]"
---

`<addon>` is the Context Editor add-on's folder in Blender and `<python>` is Blender's own Python. Take
both from the run's `context.json` (`addon_dir`, `python_bin`). With no run yet, ask Blender over the
Blender MCP server (`execute_blender_code`):
`import os, sys, context_editor; result = {"addon": os.path.dirname(context_editor.__file__), "python": sys.executable}`.
If that fails, use the setup skill. Read `<addon>/PIPELINE.md` first.

Arguments: `$ARGUMENTS`: optional run folder (default: newest), optional `live`.

**Default** (file closed in Blender):
1. Ask the artist to confirm the file at `context.json` → `source_blend` is closed in Blender.
2. `"<python>" <addon>/tools/apply.py <run>`. It copies the file to `<name>.ctx-backup-<ts>.blend`
   first, applies the kept scripts with ownership checks, and only then saves over the original. Report
   the backup path.

**`live`** (file open in Blender, over the Blender MCP server):
1. Confirm with the artist that the open file is the one to change.
2. `execute_blender_code`:
   `import runpy; result = runpy.run_path("<addon>/tools/apply_live.py", run_name="ctx_apply")["apply"]("<run>")`.
   It saves a backup copy first and doesn't save the open file.
3. Report the backup path, what was applied, and any problems as they are. Saving is the artist's call.
