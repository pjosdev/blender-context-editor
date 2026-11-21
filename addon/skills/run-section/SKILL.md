---
name: run-section
description: Rebuild one section with the artist's redo notes, then refresh the full build. Use when the artist wants a section redone.
argument-hint: "<section id> [run folder]"
---

`<addon>` is the Context Editor add-on's folder in Blender and `<python>` is Blender's own Python. Take
both from the run's `context.json` (`addon_dir`, `python_bin`). With no run yet, ask Blender over the
Blender MCP server (`execute_blender_code`):
`import os, sys, context_editor; result = {"addon": os.path.dirname(context_editor.__file__), "python": sys.executable}`.
If that fails, use the setup skill. Read `<addon>/PIPELINE.md` first.

Arguments: `$ARGUMENTS`: a section id (or its first 6 characters), then an optional run folder
(default: newest).

1. If the artist gave a reason in this request that isn't recorded yet, record it as a redo
   (PIPELINE.md "Keep / redo"). Read `feedback/<id>.md` and the section's current report.
2. `"<python>" <addon>/tools/make_copies.py <run> <id>` (rebuilds the copy with its ancestors' current
   scripts).
3. Start one worker (PIPELINE.md "Workers") with its task line from `plan.md` and the measured
   interface numbers of the built sections it attaches to, and tell it: the artist asked for a redo;
   `feedback/<id>.md` overrides everything else; continue iteration numbering after the highest
   existing `previews/<id>/iter_<n>.png`.
4. If this section has child sections that were already built, say they now sit on a changed parent and
   offer to rebuild them.
5. `"<python>" <addon>/tools/merge.py <run> --all` to refresh `build_provisional.blend`. Tell the artist
   to reopen it in Blender (File > Revert if it's open) and say keep or redo for this section. Then
   **stop**.
