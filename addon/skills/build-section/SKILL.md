---
name: build-section
description: Build one Context Editor section in headless Blender. Write its build script, render, compare with the artist's references and intent, iterate, and report. Used by workers the lead starts, one per section.
---

`<addon>` is this skill's folder's grandparent (the Context Editor add-on) and `<python>` is Blender's own
Python: both are in `RUN/context.json` (`addon_dir`, `python_bin`). Read the "Rules" in `<addon>/PIPELINE.md`.

You build **one section** of a Blender scene from the artist's context. The artist made the taste
decisions (block-out, references, intent). The block-out marks the volume and placement you work in;
it is not the final form. You rebuild the geometry inside that volume so it looks like the references
and intent, then add materials, detail and lighting. The artist judges the result; you report honestly.

## Inputs (the lead gives you these)

- `RUN`: the run folder (absolute)
- `SID`: your section id
- `ITER_LIMIT`: usually 4
- your task line from `RUN/plan.md`, and the measured interface numbers of built sections you attach to

Read, in this order:
1. `RUN/context.json`: your section (match `id`), its parent section if `parent_id` is set (inherit its
   intent, refs and notes; yours override), and `project` (style notes, palette, era, global refs and
   notes, which apply to you).
2. Your context: `refs[]`, `notes[]`, `links[]`, `sketches[]` and `groups[]` on your section (and the
   `global_*` ones on `project`).
   - A sketch is a Grease Pencil drawing the artist made in the scene: `RUN/<sketch.image>` is a render
     of your section with the drawing visible, and `RUN/<sketch.strokes>` holds its stroke points in world
     space, per layer, with each stroke's material name. The drawing object is not block-out and not
     yours to change.
   - Each entry in `groups[]` is a frame the artist drew in the Context Editor, with their own `label`,
     and can hold nested `groups[]`. **Everything inside one group is meant together**: a note in a group
     is about the images in that group. Read labels and notes as the artist wrote them; don't invent
     categories or roles they didn't give.
   - Look at every reference image (`RUN/<ref.file>`) and at your block-out preview `RUN/<blockout_preview>`.
3. `RUN/feedback/<SID>.md` if it exists: the artist asked for a redo. This overrides everything else.
4. **Script rules** below, and `<addon>/tools/ctx_runtime.py` for the helper API.
5. `objects[]` in your section: names, bounds and materials of the block-out, the volume you rebuild
   inside. `neighbors[]` are sections touching yours; keep your detail inside your bounds at the seams.

## Outputs

- `RUN/scripts/<order:02d>_<SID>.py`: the build script (`order` is in context.json)
- `RUN/previews/<SID>/iter_<n>.png`: one render per iteration
- `RUN/reports/<SID>.md`: what you built, where you departed from the references and why, what you're
  unsure about, and the measured numbers of the interfaces you provide (positions and sizes of mount
  points, openings and contact faces)
- `RUN/touched/<SID>.json`: written by the runner, not by you

## Loop (up to ITER_LIMIT)

1. Write or revise the script.
2. Run it on your working copy. The runner never saves the copy, so every run starts fresh:
   ```
   "<python>" <addon>/tools/run_section.py RUN SID N
   ```
   It runs your script on `RUN/work/SID/work.blend` with the Blender from
   `context.json`, checks idempotency, writes `RUN/touched/SID.json`, renders
   `RUN/previews/SID/iter_N.png`, and prints only the `CTX_` lines and errors. To check fit against a
   neighbour, add `--with <neighbour_id>`: it runs the neighbour's script first, writes its touched files
   to `RUN/touched/_scratch/` and renders nothing.
   `CTX_STATUS 0` = clean. Script errors (1), violations (2), conflicts (3) and non-idempotent (4) must be
   fixed before the iteration counts as a result. No render is written unless the status is 0.
3. Look at the render next to the references, the block-out preview and the intent. Write down what's
   off: shape, material, density of detail, scale, seams.
4. Stop when it matches the intent, or at the limit. Don't spend iterations on tiny changes.

## Script rules

```python
import ctx_runtime as ctx
sec = ctx.section()   # set by the runner
sec.clean()           # first line: removes this section's previous output -> idempotent
```

- Build with `sec.mesh_object`, `sec.material`, `sec.assign`, `sec.modifier`, `sec.light`,
  `sec.duplicate`, `sec.sub_collection`, `sec.node_group`. They prefix names and link into the section.
- `sec.blockout` = the artist's objects; `sec.bbox()` = their world bounds.
- `bmesh` and the data API only. No `bpy.ops` that depend on selection or UI context.
- Randomness only through `sec.rng`. No network, no file reads outside the run folder.

## Rules

- Touch only what your section owns (PIPELINE.md "Ownership"). Never the world, scene settings, other
  sections, or untagged collections. The runner's diff catches it.
- Everything new goes through the `sec.*` helpers, so it's prefixed and linked into your collection.
- **The block-out is bounds and placement, not shape.** Build new geometry inside each block-out part's
  volume with the form of the references: an engine looks like an engine, a body like a motorbike body.
  Then hide the block-out parts you replaced (`o.hide_render = o.hide_viewport = True`). Never delete or
  edit block-out meshes in place (it breaks the idempotency check). Stay roughly inside the bounds.
- Keep the interfaces your task names (openings, mount points, contact faces) so neighbours still fit,
  and meet the measured numbers the lead gave you. Parts that attach to something attach for real: a
  hose ends in a fitting on a part, a handlebar sits on a stem and clamp that meets the body. Nothing
  floats.
- **Not done:** if your final render still reads as the block-out's boxes and cylinders with paint on,
  you haven't done the job. Say so in the report if you run out of iterations.
- Real-world scale (`project.scale_unit`). Bolts are centimetres, panels are tens of centimetres.
- Don't edit `context.json`, `base.blend`, other sections' files, or anything in `<addon>`.

## Report (`reports/<SID>.md`)

```
# <title>
Iterations: N (status of the final run)
## Built
- ...
## Interfaces (measured)
- ...
## Departures from the references
- ... and why
## Unsure
- ...
```

Finish with a 3-line summary to the lead: final iteration, the final preview path, and the one thing the
artist should look at first.
