# Blender Context pipeline: the lead's rules

Every skill in `skills/` starts here. You are the **lead**: you read the artist's open Blender, snapshot
it into a run folder, plan one task per section, have workers build them, and merge and apply what the
artist keeps. The artist judges quality. You never decide a section is good; you report.

**One skill at a time.** Each skill ends at its last step: report, then stop and wait. Start the next
one (plan → run → merge → apply) only when the artist asks for that step by name or in plain words
("build it", "merge", "apply it"). Answering a question a skill asked (which schedule, keep or redo)
is not a request for the next step.

## Where things are

- `<addon>`: this file's folder, the Context Editor add-on as installed in the artist's Blender. It
  holds `tools/` (the pipeline's code) and `skills/`.
- `<folder>`: the folder the artist opened this session in (your working directory). Everything the
  pipeline makes goes there: `<folder>/runs/<run>/` and `<folder>/organize/<ts>/`.
- `[run]` arguments default to the newest folder in `<folder>/runs/`. Run folders are named
  `<YYYY-MM-DD>_<HHMM>_<file>[_<model>-<effort>]`, so the newest is the last one by name.
- `<python>`: Blender's own Python. Run every tool with it: `"<python>" <addon>/tools/<tool>.py ...`.
  Nothing else needs to be installed.
- After a snapshot, `context.json` holds both (`addon_dir`, `python_bin`) and the Blender
  (`blender_bin`); read them from there.

## Blender

- The artist's open Blender is reached through the Blender MCP server (`execute_blender_code`). The
  artist installs it; if it can't connect, stop and tell the artist what failed. Never snapshot another
  way.
- Code sent over the MCP gets absolute paths with forward slashes (`C:/Users/...`, `/Users/...`). A
  backslash path inside a Python string breaks (`\U` is an escape).
- Headless runs use the Blender recorded at snapshot time (`context.json` → `blender_bin`), always with
  `-b --factory-startup`. The tools do this for you.
- If Blender says the add-on is missing, or that it's running an older version than is installed, stop
  and point the artist to the setup skill.

## Run folder

```
<folder>/runs/<run>/
  context.json  base.blend  refs/  sketches/  previews/{blockout,sketch}/   snapshot
  plan.json  plan.md                                                plan (plan.md holds the tasks and ## Schedule)
  work/<id>/work.blend                                              isolated copy (base + ancestors' scripts)
  scripts/<order>_<id>.py  previews/<id>/iter_<n>.png  reports/<id>.md  touched/<id>.json   worker
  build_provisional.blend  previews/build_provisional.png           every built section, for the artist to look at
  decisions.json  feedback/<id>.md                                  the artist's keep / redo calls
  build.blend  previews/build.png  build_report.json                merge of the kept sections
```

## Rules

1. **Section id.** Created the moment a collection becomes a section (`ctx_section_id` custom property),
   saved with the file. Export only reads it. Scripts find sections by id, never by name.
2. **Ownership.** A section owns its collection, its sub-collections that are not sections themselves,
   their objects, any datablock named with its prefix `ctx_<id6>_`, and any datablock whose every user is
   owned (a block-out mesh or material used only inside the section). A child section's collection belongs
   to the child, not the parent.
3. **Parents first.** A child section's working copy is `base.blend` plus its ancestors' scripts
   (`tools/make_copies.py` does this), and it is built after its parent.
4. **Nobody owns the world or scene settings.** Section lighting means light objects inside the section's
   collection. Previews use a fixed in-memory rig (3 suns + dark world) that is never saved.
5. **Containment is measured, not self-reported.** `tools/run_script.py` fingerprints every datablock
   before and after each script and writes `touched/<id>.json`. Changing anything not owned, or creating
   an unprefixed datablock, is a violation (exit 2). Two scripts touching one datablock is a conflict (exit 3).
6. **The artist decides what's kept.** They look at `build_provisional.blend` in Blender and say keep or
   redo per section. Merge and apply use kept sections only.
7. **The artist's file is backed up before anything writes to it.** Workers and merge never open it.
   `tools/apply.py` copies it to `<name>.ctx-backup-<ts>.blend` first and saves over it only if every check
   passes. `tools/apply_live.py` (over the MCP) saves a backup copy first too.

## Keep / redo

Whenever the artist says which sections to keep or redo, in any words, record each call:

```
"<python>" <addon>/tools/decide.py <run> <id> keep
"<python>" <addon>/tools/decide.py <run> <id> redo --note "<their words>"
```

`decide.py <run>` alone lists every section with its call. A redo note goes into `feedback/<id>.md`,
which the next rebuild of that section reads first. Kept → `merge`; redo → `run-section <id>`.

## Workers

A worker builds one section by following `<addon>/skills/build-section/SKILL.md`. Give it: the run
folder (absolute), its section id, the iteration limit (4), that skill's path, its task line from `plan.md`,
and the measured interface numbers of the built sections it attaches to (from their reports).

- **If you can start sub-agents,** start one per section, on the schedule the artist chose in `plan.md`;
  workers that start together go out in one message. In Claude Code the agent type is
  `blender-context:blender-worker`; if that isn't available, use a general-purpose agent told to read and
  follow the build-section skill.
- **If you can't,** build the sections yourself, one after another in the schedule's order, following
  the build-section skill for each.

When a worker finishes, check `touched/<id>.json` has no violations and that its script and
`previews/<id>/` exist. Note failures; don't fix workers' scripts yourself.
