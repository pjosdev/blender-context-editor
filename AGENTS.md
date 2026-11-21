# Working on this repo

This repo is where the Blender Context Editor add-on and its agent pipeline are developed. Everything
that ships is in `addon/`: one Blender add-on that holds the board, the pipeline's code and the skills.
Read `README.md` for what it does and `addon/PIPELINE.md` for the rules the lead and workers follow.

## Layout

- `addon/`: the add-on package (`context_editor` once installed).
  - `*.py`: board, sections, export; `agent_skills.py` installs the skills.
  - `tools/`: the pipeline's code, stdlib only, run on Blender's own Python (`context.json` →
    `python_bin`). The tools import `scene_model.py` etc. from the folder above them.
  - `skills/<name>/SKILL.md` and `PIPELINE.md`: what agents read.
  - `agents/`, `.claude-plugin/`: Claude Code plugin files. `tools/build_addon.py` leaves them out of the zip.
- `.claude-plugin/marketplace.json`: the plugin listing, source `./addon`.
- `tests/`, `schema/`, `plan/` (the original spec): development only.

## Rules for changes

- Skills contain no paths. They get `<addon>` and `<python>` from `context.json` (`addon_dir`,
  `python_bin`), or from Blender over the MCP before there is a run. Keep them free of agent-specific
  syntax; Claude-only material goes in `addon/agents/` or `plugin.json`.
- A skill's folder name is its `name`. The plugin shows it as `/blender-context:<name>`; the Install agent
  skills button copies it as `ctx-<name>` and rewrites "the `<name>` skill" references to match.
- Bump `version` in `addon/__init__.py` and `addon/.claude-plugin/plugin.json` on every change in
  `addon/`. Installed skill copies carry that version, and the setup skill compares them.
- Pipeline output (`runs/`, `organize/`) goes in the session's folder, never inside `addon/`.

## Tests

```
BLENDER_BIN=/path/to/blender python3 -m unittest tests.test_pipeline -v
```

On Windows: `$env:BLENDER_BIN="C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"` then
`python -m unittest tests.test_pipeline -v`. The Addon test installs the zip into a throwaway Blender
user folder and runs the setup checks, the skills install and a snapshot from the installed copy.
Plugin checks: `claude plugin validate .` and `claude plugin validate ./addon`; try it with
`claude --plugin-dir ./addon`, `/reload-plugins` after edits.

## Windows

- `os.kill(pid, 0)` terminates a process on Windows; `tools/wait_previews.py` uses `OpenProcess` instead.
- Read and write text as UTF-8 explicitly (the Windows default is cp1252); Blender output too.
- Background Blender runs from the add-on use `CREATE_NO_WINDOW`.
- In code sent over the MCP, paths use forward slashes (`\U` in a Python string is an escape).
