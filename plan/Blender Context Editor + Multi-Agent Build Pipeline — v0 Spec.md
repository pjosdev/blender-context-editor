# Blender Context Editor + Multi-Agent Build Pipeline — v0 Spec

Nov 19, 2026 · @pjos

## Overview

v0 is a Blender add-on plus a Claude Code project setup that lets an artist attach structured creative context to parts of a scene, then hand that context to a lead Claude agent that splits the work across parallel workers and returns runnable Blender Python scripts.

**The problem.** A vague prompt ("make a sick 80s interior") forces the model to make every taste decision itself, so it falls back to the average of its training data: competent, generic, roughly 6/10.

**The principle.** The artist supplies the taste as inputs (block-out, real references, per-section intent) and hones the outputs by hand. The AI does the middle: the volume of execution between a strong input and a finished-sized result.

**Three parts:**

1. **Context Editor**: a custom node editor inside Blender that works like a PureRef board linked to scene collections.
2. **Context export**: a machine-readable JSON snapshot of that board plus scene metadata.
3. **Orchestration pipeline**: a Claude Code session that acts as lead, reads the export, assigns per-section tasks to workers, has each worker iterate in headless Blender on its own copy, and merges the results.

## Goals and non-goals

v0 succeeds if one artist can take a blocked-out model with three tagged sections through the full loop and get back per-section scripts that run cleanly on the original file.

**Goals**

- Tag collections as named sections with intent notes, references and links, from inside Blender.
- Show that context on a node-based board in its own editor.
- Export the board to a stable JSON file that an agent can read without opening Blender.
- Run a lead agent that turns the export into one task per section.
- Run workers in parallel against isolated copies via headless Blender, each producing a script and preview renders.
- Merge the scripts into an ordered build that applies to the original file and can be rerun.

**Non-goals for v0**

- No judgment of aesthetic quality by the system. The artist is the judge.
- No live multi-user editing of the .blend file.
- No automatic downloading or scraping of reference images. The artist provides them.
- No texture painting, rigging, animation or simulation. Modeling, materials and lighting only.
- No custom orchestrator. Claude Code is the harness; the repo only adds its agent definitions, slash commands and helper scripts.

## Artist workflow

The artist's job is to make the decisions that carry quality, then hand off the middle.

1. **Block out.** Model the silhouette and massing. Add enough detail that proportions read correctly.
2. **Organize into sections.** Group objects into collections (COCKPIT, WING\_L, ENGINE\_CLUSTER). Use sub-collections when a set of objects needs its own context, such as COCKPIT/SEATS.
3. **Build the context board.** In the Context Editor, add a Section node for each collection. Attach real reference images, material links, and intent notes. Write specifics ("Alien-style CRT bank, beige plastic, yellowed with age"), not adjectives ("make it cool").
4. **Export.** One button writes `context.json` and a snapshot of the .blend file.
5. **Run the pipeline in Claude Code.** The lead agent plans tasks per section. Workers build, render previews, and iterate against the references.
6. **Review per section.** The artist sees preview renders for each section and accepts, rejects with a note, or edits the context and reruns that section.
7. **Apply and hone.** Accepted scripts are applied to the original file in order. The artist does the final passes by hand.

## Architecture

&#91;embedded content: v0 pipeline · 5 stages, 3 parallel workers\]

Workers never touch the original file. A rejected section reruns on its own, with the artist's note added to its context.

## Component A: Context Editor add-on

The Context Editor is a custom node tree type, registered by the add-on, that appears in the node editor's tree-type dropdown next to Shader and Geometry Nodes. The tree is a datablock in `bpy.data.node_groups`, so it saves inside the .blend file.

**Editor and workspace.** Add-ons can't register a brand-new editor type in Python; that takes C. A custom node tree is the supported route and gives the same experience as the Shader Editor: in any Node Editor area, pick Context Editor from the tree-type dropdown and it behaves like a native editor, with its own Add menu, header and sidebar.

- **Context workspace.** On first use, the add-on creates a Context workspace tab next to Shading: 3D viewport on the left, Context Editor on the right.
- **Node editor sidebar (N-panel), Context tab**, for fast setup: Make Section from the active collection, a list of all sections with their status, and quick-add buttons that attach Reference, Note and Link nodes to the selected section.
- **Drag and drop.** Dropping image files on the Context Editor creates Reference Image nodes, using the `FileHandler` API (available in 5.2). If a Section node is selected, they attach to it.
- **Selection sync (stretch goal).** Selecting a Section node selects its collection's objects in the viewport, and the reverse.

**Tree type**

- `ContextTree(bpy.types.NodeTree)`, `bl_idname = "CTX_ContextTree"`, label "Context Editor".
- One tree per .blend file in v0. Created on first use.
- Built-in Frame and Reroute nodes are available for grouping. A Frame can show the contents of a Text datablock, which is useful for long notes.

**Node types**

| Node | Properties | Sockets |
| --- | --- | --- |
| Project | `style_notes` (Text datablock), `era`, `scale_unit`, `palette` (list of hex strings) | Output: Context, which applies to all sections |
| Section | `collection` (PointerProperty to Collection), `title`, `intent` (Text datablock), `status` (draft, ready, locked), `order` (int) | Input: Context, multi-input |
| Reference Image | `image` (PointerProperty to Image), `caption`, `take` (shape, material, lighting, mood), `strength` (match closely, loosely, mood only) | Output: Context |
| Note | `kind` (intent, constraint, avoid), `text` (string or Text datablock) | Output: Context |
| Link | `url`, `label`, `kind` (material, tutorial, product, other); draws an Open button that calls `wm.url_open` | Output: Context |

Context nodes attach to a section by linking their output into the section's multi-input socket. Anything linked into the Project node applies globally.

**Drawing**

- Reference Image nodes show a thumbnail: call `image.preview_ensure()`, then `layout.template_icon(icon_value=image.preview.icon_id, scale=N)`.
- Section nodes show the collection's name, object count, and status as a colored header.

**3D viewport sidebar panel**

- "Context" tab in the N-panel. It shows the section that contains the active object, with its intent and reference captions.
- Buttons: Make Section from Active Collection, Jump to Node, Export Context.

**Section hierarchy** comes from the collection hierarchy, not from links between nodes. A section for COCKPIT/SEATS is a child of COCKPIT automatically. Children inherit their parent's context, and their own context overrides it.

**Mirroring to the scene.** On export, each tagged collection gets a custom property `ctx_section_id`, so scripts can find sections without parsing the tree.

Target Blender 5.2 LTS only. Check API calls against the 5.2 Python API docs, because node and preview APIs have changed between releases.

## Component B: Context export

Export writes a self-contained run folder, so agents never need the live Blender session to understand the project.

**Run folder layout**

```
runs/<timestamp>/
  context.json        # the board + scene metadata
  base.blend          # snapshot of the file at export time
  refs/               # copies of every reference image
  previews/blockout/  # one render per section, before any work
```

**context.json, v0 schema**

- `schema_version`: `"0.1"`
- `project`: `style_notes`, `era`, `scale_unit`, `palette`, `global_refs[]`, `global_notes[]`, `global_links[]`
- `sections[]`, one per Section node:
  - `id` (stable UUID, also written to the collection as `ctx_section_id`), `title`, `collection_path` (e.g. `"SHIP/COCKPIT"`), `parent_id`, `status`, `order`
  - `intent`: full text
  - `refs[]`: `file` (path relative to the run folder), `caption`, `take`, `strength`
  - `notes[]`: `kind`, `text`
  - `links[]`: `url`, `label`, `kind`
  - `objects[]`: `name`, `type`, `vertex_count`, `bbox_world` (min and max), `materials[]`
  - `blockout_preview`: path to that section's render
  - `neighbors[]`: ids of sections whose bounding boxes touch this one, so workers know where seams are

**Example (trimmed)**

```json
{
  "schema_version": "0.1",
  "project": {
    "era": "1980s industrial sci-fi",
    "scale_unit": "m",
    "style_notes": "Used future. Nothing is new. Function over form.",
    "palette": ["#C8B89A", "#3A3F44", "#E0A030"]
  },
  "sections": [
    {
      "id": "7b1e...",
      "title": "Cockpit interior",
      "collection_path": "SHIP/COCKPIT",
      "status": "ready",
      "intent": "Cramped two-seat cockpit. CRT bank overhead, chunky toggle switches, beige plastic yellowed with age.",
      "refs": [
        {"file": "refs/crt_bank_01.jpg", "caption": "Overhead CRT layout", "take": "shape", "strength": "match closely"}
      ],
      "notes": [{"kind": "avoid", "text": "No touchscreens, no glowing blue holograms."}],
      "links": [{"url": "https://example.com/worn-plastic-material", "label": "Worn plastic", "kind": "material"}],
      "objects": [{"name": "cockpit_shell", "type": "MESH", "vertex_count": 412}],
      "blockout_preview": "previews/blockout/7b1e.png",
      "neighbors": ["a90c..."]
    }
  ]
}
```

## Component C: Orchestration pipeline

For v0, the lead is a Claude Code session and workers are its subagents, each running headless Blender through the shell. Workers don't need to talk to each other, so subagents are enough. Claude Code's experimental agent teams can come later.

**Claude Code setup.** The repo makes Claude Code the harness through its own configuration, with no separate orchestrator program:

- `CLAUDE.md`: the lead's instructions, covering pipeline steps, file layout and script rules.
- `.claude/agents/blender-worker.md`: a custom subagent definition for workers, with its prompt and allowed tools.
- `.claude/commands/`: one slash command per step: `/ctx-plan`, `/ctx-run`, `/ctx-run-section <id>`, `/ctx-merge`, `/ctx-review`.
- `tools/`: plain Python and Blender scripts that agents call through the shell for the deterministic work (copies, preview renders, merge, conflict check), so agents spend their effort on the build scripts.
- Optional: the Blender MCP server in Claude Code's MCP config, for the final apply to the live session.

**Lead agent**

1. Read `context.json` and the block-out previews.
2. Write `plan.md`: one task per section with status `ready`, in `order`, noting dependencies (a child section builds after its parent).
3. Make an isolated working copy for each task: `work/<section_id>/work.blend`, copied from `base.blend`.
4. Dispatch one worker per task, running in parallel up to a limit (default 3).
5. Collect results, run the merge, and write `review.md` for the artist.

**Worker contract**

Inputs: its section object from `context.json`, inherited project and parent context, its reference images, and its working copy.

Outputs:

- `scripts/<order>_<section_id>.py`: the build script
- `previews/<section_id>/iter_<n>.png`: one render per iteration
- `reports/<section_id>.md`: what it built, where it departed from the references and why, and what it is unsure about

Loop, up to 4 iterations:

1. Write or revise the script.
2. Run it on a fresh copy of `base.blend`: `blender -b --factory-startup work.blend --python script.py -- --render previews/<id>/iter_<n>.png`.
3. Look at the render next to the references and the intent. Note what's off.
4. Stop when it matches the intent, or when the iteration limit is reached.

**Script rules** (enforced by a shared helper module, `ctx_runtime.py`)

- Find the owned collection by `ctx_section_id`, never by name alone.
- Create and modify only objects inside the owned collection. Never delete anything outside it.
- Prefix new datablocks: `ctx_<section_short>_` for objects, materials and node groups.
- Be idempotent: running twice gives the same result. Remove the section's own `ctx_` datablocks before rebuilding.
- Deterministic: fixed random seeds. No network access.
- Every touched datablock is logged to `touched/<section_id>.json` so the merge can detect conflicts.

**Preview renders**

- EEVEE, low samples, 1024 px, about 10 seconds per frame.
- Camera: use `CTX_CAM_<section>` if the artist placed one. Otherwise auto-frame the section's bounding box from a three-quarter angle.
- Same camera and lighting for every iteration, so renders can be compared.

**Merge**

1. On a fresh copy of `base.blend`, run accepted scripts in `order`.
2. Fail if two scripts touched the same datablock. Report the conflict to the artist instead of guessing.
3. Save `build.blend` and render a full-model preview.
4. Apply to the live file in one of two ways: the artist opens `build.blend`, or the lead runs the same ordered scripts through the Blender MCP connection.

**Review gate**

`review.md` lists each section with its block-out preview, final preview, reference thumbnails and the worker's report. The artist marks each section accept or reject. A reject includes a note in `feedback/<section_id>.md`. `/ctx-run-section <id>` reruns one section with that feedback added to its context.

## Repo layout and constraints

```
blender-context/
  addon/
    __init__.py          # bl_info, register/unregister
    tree.py              # ContextTree + node and socket classes
    ui.py                # node editor sidebar, viewport panel, workspace setup
    file_handler.py      # drag-and-drop images into the Context Editor
    export.py            # context.json + run folder writer
  tools/
    ctx_runtime.py       # helpers every build script imports
    make_copies.py       # isolated .blend copy per section
    render_preview.py    # camera framing + EEVEE preview render
    merge.py             # ordered apply + conflict check
  .claude/
    agents/
      blender-worker.md  # worker subagent definition
    commands/
      ctx-plan.md
      ctx-run.md
      ctx-run-section.md
      ctx-merge.md
      ctx-review.md
  CLAUDE.md              # lead instructions: pipeline, layout, script rules
  examples/
    ship_blockout.blend  # test scene with 3 tagged sections
  tests/
```

**Constraints**

- Blender 5.2 LTS's bundled Python interpreter for anything that imports `bpy`.
- The add-on has no dependencies beyond `bpy`. Scripts in tools/ use the standard library only in v0.
- The Blender binary path comes from `BLENDER_BIN` (environment variable), so it works on macOS, Windows and Linux.
- Headless runs always use `--factory-startup`, so the artist's own add-ons and preferences can't affect results.
- The original .blend is never written to by workers. Only the merge step or the artist changes it.

## Build order and acceptance criteria

Build in this order. Each step is usable and testable before the next starts.

1. **Add-on skeleton.** Context Editor tree type and the five node types register and save with the file.
2. **Export.** Run folder, `context.json`, reference copies, block-out previews.
3. **Runtime + single worker.** `ctx_runtime.py`, preview renderer, and one worker building one section end to end, without parallelism.
4. **Merge.** Ordered apply on a fresh copy, conflict check, `build.blend`.
5. **Lead + parallel workers.** Planning, isolated copies, up to 3 workers at once.
6. **Review loop.** `review.md`, accept or reject, and rerunning a single section with feedback.

**v0 is done when:**

- [ ] The add-on installs on a clean Blender 5.2 LTS and the Context Editor shows up in the node editor's tree-type dropdown.
- [ ] Save, close and reopen keeps every node, link, image and note intact.
- [ ] Export of `examples/ship_blockout.blend` produces a `context.json` that validates against the schema.
- [ ] Each worker's script runs on a fresh `base.blend` with `--factory-startup` and gives the same result twice.
- [ ] No script modifies a datablock outside its own section. The touched-datablock logs prove this.
- [ ] Three sections build in parallel and merge into `build.blend` with no conflicts.
- [ ] A deliberately conflicting script makes the merge stop with a clear message.
- [ ] Rejecting one section and rerunning it changes only that section.
- [ ] The original .blend file's modification time doesn't change during a run.

## Risks and open questions

**Risks**

- **Code-driven modeling quality.** Scripted hard-surface work tends toward rough edge flow and uneven detail density. Mitigation: keep v0 to additive detail, materials and lighting on top of the artist's block-out, not remodeling.
- **Seams between sections.** Workers that can't see each other may build mismatched edges where sections meet. Mitigation: `neighbors[]` in the export, plus a seam check in the full-model preview.
- **Render-based self-checks are weak.** A worker comparing its render to the references is a rough 7/10 filter at best. The artist's review is the real gate.
- **Blender API drift.** Node, preview and EEVEE APIs change between versions. Pin a tested version and run the tests against it.

**Open questions**

- Should Section nodes link to each other to express relationships that the collection hierarchy can't, such as "this panel should match that one"?
- Do material links point to downloadable assets the pipeline should fetch, or are they only reference for the worker?
- Should accepted scripts be committed to git alongside the .blend, as the reproducible record of a build?
- At what point is it worth moving from subagents to agent teams, so workers on neighboring sections can coordinate seams directly?
