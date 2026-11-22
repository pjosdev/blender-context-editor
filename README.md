# Blender Context Editor + build pipeline

A Blender add-on and an agent pipeline for turning a block-out into a detailed model.

- **The artist supplies the taste:** a block-out, collections tagged as *sections*, and per-section
  reference images, notes and Grease Pencil sketches on a node board inside Blender.
- **Agents do the volume of execution:** a lead agent snapshots the open file and plans one task per
  section. Worker agents each write a Python build script for their section, run it in headless
  Blender, look at the renders, and iterate.
- **The artist reviews in Blender,** says keep or redo per section, and the kept sections are merged and
  applied to the file.

Blender 5.2 LTS. Everything is in one Blender add-on: the board, the pipeline's code (which runs on
Blender's own Python, so there is nothing else to install) and the skills that tell an agent what to do.
Works with Claude Code and with other agents that read `~/.agents/skills` (Codex, Gemini CLI, Cursor ...).

## Install

1. **The Context Editor add-on:** download `context_editor.zip` from the
   [latest release](https://github.com/pjosdev/blender-context-editor/releases/latest), then in Blender
   Edit > Preferences > Add-ons > Install from Disk, pick the zip, and enable **Context Editor**.
   (To build it from this repo instead: `python addon/tools/build_addon.py` → `dist/`.)
2. **A Blender MCP add-on,** so your agent can talk to Blender. Install it in Blender, enable it, start its
   server, and connect it to your agent. The pipeline reads and changes your open file only through it.
3. **The skills,** one of:
   - In the Context Editor's add-on preferences, tick your agents and press **Install agent skills**. It
     copies them into `~/.agents/skills` (other agents) and/or `~/.claude/skills` (Claude Code) as
     `ctx-setup`, `ctx-plan` and so on, or into another folder you choose (e.g. one project's
     `.agents/skills`). Press it again after updating the add-on.
   - Claude Code, as a plugin: `/plugin marketplace add pjosdev/blender-context-editor`, then
     `/plugin install blender-context@blender-context-editor`. The commands are then
     `/blender-context:plan` and so on, and its setup can install the add-on for you.
4. Ask your agent to run the **setup** skill. It checks the connection, the add-on and the skills, and
   fixes what it can.

Open your agent in the folder you want the work to go in. Each snapshot goes in `runs/` there, and
`organize` passes go in `organize/`.

## Artist workflow

1. Block out. Group objects into collections; use sub-collections for parts that need their own context.
2. 3D View sidebar > Context > **Make Section from Active Collection**. This opens a **Context** workspace:
   the 3D view on the left and the Context Editor on the right.
3. In the Context Editor:
   - set each section to **Ready**;
   - attach Reference Image, Note, Link and Grease Pencil nodes (drag image files onto the editor);
   - use frames to group refs with the note about them;
   - anything linked into the Project node applies to every section.
   Images and notes on the board are kept with the file automatically.
4. Save the file, then in your agent:

| Skill (Claude Code) | Other agents | What it does |
| --- | --- | --- |
| `/blender-context:setup` | `ctx-setup` | Checks the Blender connection, installs or updates the add-on |
| `/blender-context:plan` | `ctx-plan` | Snapshots the open Blender into `runs/<run>/` (your .blend is not saved or changed), writes the plan, and asks which worker schedule to use |
| `/blender-context:run` | `ctx-run` | Builds every section on that schedule, then makes `build_provisional.blend` for you to open and say keep or redo per section |
| `/blender-context:run-section <id>` | `ctx-run-section` | Rebuilds one section with your redo notes |
| `/blender-context:merge` | `ctx-merge` | Kept sections → `build.blend` |
| `/blender-context:apply` | `ctx-apply` | Backs up your .blend, then applies the kept sections to it (`live` = in the open Blender) |
| `/blender-context:organize [notes]` | `ctx-organize` | Renames and sorts every object into collections; backup first, one Ctrl+Z undoes it |

`[run]` defaults to the newest folder in `runs/`. Run folders are named `<YYYY-MM-DD>_<HHMM>_<file>`
(e.g. `2026-11-20_1318_myscene`); `run` appends the model that builds it (`…_opus-xhigh`).

Workers run as sub-agents where the agent supports them (in Claude Code, the `blender-worker` agent).
Otherwise the lead builds the sections itself, one after another. Workers need image input, because they
judge their own renders against the references.

## Repo layout

| Path | What |
| --- | --- |
| `addon/` | The add-on, `context_editor`, and everything that ships. Also the Claude Code plugin root. |
| `addon/*.py` | The node board, section tagging, the export. `scene_model.py` holds section and ownership logic and is also imported by the tools; `agent_skills.py` is the Install agent skills button. |
| `addon/PIPELINE.md` | The lead's rules: ownership, containment, parents first, backups, keep/redo, workers. Every skill reads it first. |
| `addon/skills/` | One folder per skill. `build-section` is the worker's contract; the lead hands it to workers. |
| `addon/tools/` | The pipeline's code (snapshot, plan, copies, run, decide, merge, apply, organize) plus `ctx_runtime.py`, the helper every build script imports. Stdlib only, run on Blender's Python. |
| `addon/agents/`, `addon/.claude-plugin/` | Claude Code plugin files; left out of the zip. |
| `.claude-plugin/marketplace.json` | Lets Claude Code install the plugin from this repo. |
| `AGENTS.md` | Notes for agents working on this repo. |
| `schema/context.schema.json` | Schema of the snapshot (`context.json`). |
| `tests/` | `test_pipeline.py` (unittest, needs `BLENDER_BIN`; builds its own test scene with `make_test_scene.py`) and a UI smoke test. |
| `plan/` | The original design spec. |

Not in git: `runs/`, `organize/`, `dist/` (built add-on zip), backups.

## How a run works

```
runs/<run>/
  context.json  base.blend  refs/  previews/blockout/      snapshot (from the add-on's export)
  plan.json  plan.md                                       one task per ready section, and the schedule
  work/<id>/work.blend                                     each section's isolated copy (base + ancestors' scripts)
  scripts/<order>_<id>.py                                  the deliverable: one build script per section
  previews/<id>/iter_<n>.png   reports/<id>.md             worker renders and report
  touched/<id>.json                                        runner's datablock diff (containment proof)
  build_provisional.blend                                  every built section, for you to look at
  decisions.json  feedback/<id>.md                         your keep / redo calls
  build.blend                                              merge of the kept sections
```

- **A section's output is a script, not a .blend.** Scripts use `bmesh` and the data API through
  `ctx_runtime.py`: `sec.clean()` first, so reruns are idempotent; `sec.mesh_object`, `sec.material` and so
  on prefix every new datablock with `ctx_<id6>_`.
- **Scripts run only through `tools/run_script.py`.** It fingerprints every datablock before and after.
  Touching anything the section doesn't own exits 2; two sections touching one datablock exits 3.
- **Merge** runs every kept script in order on a fresh `base.blend`. Scripts are deterministic (`sec.rng`
  only), so a build is reproducible from `base.blend` + `scripts/`.

## Known limits

- No check yet for problems in generated geometry: parts not joined, overlapping faces, flipped normals,
  missing UVs, very heavy sections.
- A section's worker uses a lot of tokens: expect a few hundred thousand per section.

## Windows

Tested on Windows 11 with Blender 5.2.

## Tests

```
BLENDER_BIN=/path/to/blender python3 -m unittest tests.test_pipeline -v
```

Windows: `$env:BLENDER_BIN="C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"` then
`python -m unittest tests.test_pipeline -v`.

UI smoke test (opens a Blender window briefly, with a separate preferences folder):
`$BLENDER_BIN -b --factory-startup --python tests/make_test_scene.py -- /tmp/ctx_ui/ship.blend`, then
`BLENDER_USER_RESOURCES=/tmp/ctx_ui $BLENDER_BIN --factory-startup /tmp/ctx_ui/ship.blend --python tests/ui_smoke.py -- /tmp/ctx_ui`

## Licence

GPL-3.0-or-later. See `LICENSE`.
