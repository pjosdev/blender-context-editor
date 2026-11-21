---
name: run
description: Build every planned section with workers on the artist's chosen schedule, then make a full build for the artist to look at in Blender. Use after plan.
argument-hint: "[run folder]"
---

`<addon>` is the Context Editor add-on's folder in Blender and `<python>` is Blender's own Python. Take
both from the run's `context.json` (`addon_dir`, `python_bin`). With no run yet, ask Blender over the
Blender MCP server (`execute_blender_code`):
`import os, sys, context_editor; result = {"addon": os.path.dirname(context_editor.__file__), "python": sys.executable}`.
If that fails, use the setup skill. Read `<addon>/PIPELINE.md` first.

Run folder: `$ARGUMENTS` (empty = newest). If it has no `plan.json`, do the `plan` skill first.

1. **Label the run** with the model and effort the workers will use (yours if you don't pick another):
   `"<python>" <addon>/tools/name_run.py <run> <model>-<effort>`, e.g. `opus-xhigh`, `fable-high`. It
   prints the new path; use it from here on. Skip if the name already ends with that label.
2. **Schedule:** follow `Chosen:` under `## Schedule` in `plan.md`. If there is none, ask the artist to
   pick from the options there (default: dependency order, 3 at a time). Parents always go before their
   children (plan.json waves).
3. **For each section, when its turn comes:**
   1. `"<python>" <addon>/tools/make_copies.py <run> <id>`. A child's copy includes its parent's
      script, so the parent must be done first.
   2. Start its worker as PIPELINE.md "Workers" says: run folder, section id, iteration limit 4,
      `<addon>`, its task line from `plan.md`, and the measured interface numbers from the reports of
      the sections it attaches to that are already built (it may run their scripts before its own with
      `run_section.py --with`).
   3. When it finishes, check it (PIPELINE.md "Workers"). Pass its measured numbers to any running
      worker that attaches to it, then start whatever its finish unblocks.
4. **Full build:** `"<python>" <addon>/tools/merge.py <run> --all`. It writes `build_provisional.blend`
   with every built section. Look at `previews/build_provisional.png` and report conflicts or visible
   seam problems as they are.
5. **Hand over to the artist:**
   - one line per section from its report, plus the thing to look at first;
   - tell them to open `<run>/build_provisional.blend` in Blender (a separate file; theirs is untouched)
     and say keep or redo for each section, with a note for each redo.
   Then **stop**. When they answer, record it as PIPELINE.md "Keep / redo" says, say what's kept and
   what's for redo, and stop again: merging, applying and rebuilds wait until they ask.
