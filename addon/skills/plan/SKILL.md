---
name: plan
description: Snapshot the artist's open Blender and plan one build task per ready section, then let the artist pick the worker schedule. Use to start a build, or to re-plan an existing run.
argument-hint: "[run folder]"
---

`<addon>` is the Context Editor add-on's folder in Blender and `<python>` is Blender's own Python. Take
both from the run's `context.json` (`addon_dir`, `python_bin`). With no run yet, ask Blender over the
Blender MCP server (`execute_blender_code`):
`import os, sys, context_editor; result = {"addon": os.path.dirname(context_editor.__file__), "python": sys.executable}`.
If that fails, use the setup skill. Read `<addon>/PIPELINE.md` first.

Arguments: `$ARGUMENTS`. Empty = make a fresh snapshot (steps 1–2). A run folder = plan that run
(skip to step 3).

1. **Snapshot,** over the Blender MCP server's `execute_blender_code`:
   `import runpy; result = runpy.run_path("<addon>/tools/snapshot_live.py", run_name="ctx_snapshot")["snapshot"]("<addon>", "<folder>")`.
   If it can't connect or `result` has `error`, stop and tell the artist exactly what it says (a missing
   or old add-on → the `setup` skill). If `unsaved_changes` is true, tell the artist the snapshot used
   the file as it is in Blender now, unsaved edits included.
2. `"<python>" <addon>/tools/wait_previews.py <run_dir>` (in the background if it may take over two
   minutes). On failure, report its output and stop.
3. `"<python>" <addon>/tools/plan.py <run>`. It writes `plan.json` (waves) and a `plan.md` skeleton.
4. Read `context.json` and look at every block-out preview in `previews/blockout/` and every sketch
   render in `previews/sketch/`.
5. Fill in each "Task:" line in `plan.md` (see **Writing tasks** below).
6. Add a `## Schedule` section to `plan.md`:
   - **Attach order:** for each section, the sections whose built surfaces it attaches to (e.g. Seat ←
     Body; Storage ← Generator, Seat). A section can start once those are built, so its worker gets their
     *measured* interface numbers. Parent sections (plan.json waves) always come first.
   - **Options,** at least these two, as a table with expected wall time, peak workers, usage burst (how
     fast the usage window fills), machine load (one headless Blender per worker) and seam risk:
     - *Dependency order, 3 at a time*: slowest, gentlest on the machine and the usage window, best seams.
     - *Parallel*: everything whose dependencies are met runs at once (up to N). Faster, but a heavier
       burst and more render contention; with N = all, sections guess their neighbours, so seams rely on
       the plan's fixed interfaces only.
     Add a middle option if one is obviously useful (e.g. "Body alone, then the rest up to 6"). If you
     can't start sub-agents, the only option is one at a time, in attach order.
   - Your recommendation and why, in one line.
7. Show the artist the run folder, the tasks as a short list, and the schedule options. Ask which
   schedule to use.
8. When they answer, write it into `plan.md` as `Chosen: …` under `## Schedule`, say the plan is ready
   and that the `run` skill starts the build when they want it, and **stop**. Their answer picks a
   schedule; it is not a request to build. Start nothing else in this turn.

## Writing tasks

One or two concrete sentences per section: what its worker should build, drawn from its intent, refs,
sketches, notes and the inherited project context. What earlier runs taught:

- **Form first,** then material. Quote the artist's notes word for word. Material-only task lines get
  material-only results.
- **The block-out is the volume to work in, not the shape to keep.** Say what the part should become;
  workers rebuild the form inside the block-out and hide the replaced pieces.
- **Fixed interfaces at the seams.** Sibling sections can't see each other's output while they build.
  Name the contact surfaces with coordinates from the block-out (seat line, steering head, mount points,
  openings, underside), so both sides meet.
- **But only the real contact patches.** Pinning too many interfaces locks a section to the block-out's
  silhouette.
- **Decals or other loose image files** the artist mentions but didn't link in the .blend: copy them into
  `<run>/refs/` and name them in the task.
