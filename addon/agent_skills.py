"""Install the pipeline's skills for coding agents, from the add-on's own skills/ folder.

Edit > Preferences > Add-ons > Context Editor > Install agent skills, or over the Blender MCP server:

    import context_editor.agent_skills as s; result = s.install(["agents", "claude"])
    result = s.install(["custom"], root="D:/my/agent/skills")      # any folder an agent reads skills from

Each skill is copied to <target>/ctx-<name>/SKILL.md with a version line. A copy is only overwritten
or removed if it carries that line, so skills the user wrote themselves are never touched. The
skills read everything else (rules, tools) from the installed add-on, so updating the add-on and
installing again keeps them in step. Needs no bpy, so the tests can call it directly.
"""

import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
SKILLS = os.path.join(HERE, "skills")
PREFIX = "ctx-"
MARK = "<!-- installed by the Context Editor add-on, version %s -->"
WORKER_ONLY = {"build-section"}  # the lead hands workers its path inside the add-on
TARGETS = {
    "agents": "~/.agents/skills",   # Codex, Gemini CLI, Cursor, ...
    "claude": "~/.claude/skills",   # Claude Code without the plugin
}


def version():
    with open(os.path.join(HERE, "__init__.py"), encoding="utf-8") as f:
        m = re.search(r'"version":\s*\((\d+),\s*(\d+),\s*(\d+)\)', f.read())
    return ".".join(m.groups())


def skill_names():
    return sorted(n for n in os.listdir(SKILLS)
                  if n not in WORKER_ONLY and os.path.isfile(os.path.join(SKILLS, n, "SKILL.md")))


def _ours(path):
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return "<!-- installed by the Context Editor add-on" in f.read()


def _copy_text(name, ver):
    with open(os.path.join(SKILLS, name, "SKILL.md"), encoding="utf-8") as f:
        text = f.read()
    text = re.sub(r"^name: .*$", "name: %s%s" % (PREFIX, name), text, count=1, flags=re.M)
    # other skills by their installed names: "the `plan` skill" -> "the `ctx-plan` skill"
    text = re.sub(r"the `([a-z-]+)` skill", lambda m: "the `%s%s` skill" % (PREFIX, m.group(1)), text)
    text = re.sub(r"the (setup|plan|run|merge|apply|organize) skill", r"the %s\1 skill" % PREFIX, text)
    head, sep, body = text.partition("\n---\n")
    return head + sep + "\n" + MARK % ver + "\n" + body


def _target(which, root=None):
    return os.path.normpath(os.path.expanduser(root or TARGETS[which]))


def install(which=("agents",), root=None):
    """Copy the skills into each target in ``which``. ``root`` overrides the folder (tests).
    Returns {"version", "written": [...], "skipped": [...]}."""
    ver, written, skipped = version(), [], []
    for w in which:
        base = _target(w, root)
        for name in skill_names():
            out = os.path.join(base, PREFIX + name, "SKILL.md")
            if _ours(out) is False:
                skipped.append(out)
                continue
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(out, "w", encoding="utf-8", newline="\n") as f:
                f.write(_copy_text(name, ver))
            written.append(out)
    return {"version": ver, "written": written, "skipped": skipped}


def remove(which=("agents",), root=None):
    removed = []
    for w in which:
        base = _target(w, root)
        for name in skill_names():
            d = os.path.join(base, PREFIX + name)
            if _ours(os.path.join(d, "SKILL.md")):
                os.remove(os.path.join(d, "SKILL.md"))
                if not os.listdir(d):
                    os.rmdir(d)
                removed.append(d)
    return {"removed": removed}


def installed_version(which="agents", root=None):
    """Version of the copies in a target, or None if they aren't installed."""
    p = os.path.join(_target(which, root), PREFIX + "plan", "SKILL.md")
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as f:
        m = re.search(r"Context Editor add-on, version ([\d.]+)", f.read())
    return m.group(1) if m else None


def _status(which, root):
    """One line for the preferences: where it goes and what's there."""
    path = _target(which, root)
    shown = (root or TARGETS[which]).replace(os.sep, "/")
    if not os.path.isdir(path):
        return "%s (not found)" % shown
    v = installed_version(which, root)
    return "%s (%s)" % (shown, "skills %s" % v if v else "found, no skills yet")


# ---------------------------------------------------------------- preferences UI (Blender only)

try:
    import bpy
    from bpy.props import BoolProperty, StringProperty
except ImportError:  # imported by the tests without Blender
    bpy = None

if bpy is not None:
    NAMES = {"agents": "Other agents", "claude": "Claude Code"}

    class CTX_OT_install_skills(bpy.types.Operator):
        """Copy the pipeline's skills into your coding agents' skills folders"""

        bl_idname = "ctx.install_skills"
        bl_label = "Install agent skills"

        missing_choice: bpy.props.EnumProperty(
            name="Missing folder",
            items=[("CREATE", "Create it in my home folder", "Make the default folder and install there"),
                   ("CUSTOM", "Use another folder", "Install into a folder you pick instead")])
        folder: StringProperty(name="Folder", subtype="DIR_PATH")

        def _missing(self, context):
            prefs = context.preferences.addons[__package__].preferences
            return [w for w, on in (("agents", prefs.skills_agents), ("claude", prefs.skills_claude))
                    if on and not os.path.isdir(_target(w))]

        def invoke(self, context, event):
            if self._missing(context):
                return context.window_manager.invoke_props_dialog(self, width=420)
            return self.execute(context)

        def draw(self, context):
            col = self.layout.column()
            for w in self._missing(context):
                col.label(text="%s: %s doesn't exist yet." % (NAMES[w], TARGETS[w].replace(os.sep, "/")),
                          icon="ERROR")
            col.prop(self, "missing_choice", expand=True)
            if self.missing_choice == "CUSTOM":
                col.prop(self, "folder", text="")

        def execute(self, context):
            prefs = context.preferences.addons[__package__].preferences
            which = [w for w, on in (("agents", prefs.skills_agents), ("claude", prefs.skills_claude)) if on]
            missing = self._missing(context)
            roots = []  # (target, root or None)
            if missing and self.missing_choice == "CUSTOM":
                folder = bpy.path.abspath(self.folder).strip()
                if not folder or not os.path.isdir(folder):
                    self.report({"WARNING"}, "Pick a folder that exists")
                    return {"CANCELLED"}
                roots.append(("custom", folder))
                which = [w for w in which if w not in missing]
            roots += [(w, None) for w in which]
            if prefs.skills_custom:
                custom = bpy.path.abspath(prefs.skills_custom_dir).strip()
                if not custom or not os.path.isdir(custom):
                    self.report({"WARNING"}, "The custom folder doesn't exist: %s" % (custom or "none chosen"))
                    return {"CANCELLED"}
                roots.append(("custom", custom))
            if not roots:
                self.report({"WARNING"}, "Tick at least one place to install to")
                return {"CANCELLED"}
            written, skipped = [], []
            for w, root in roots:
                r = install([w], root=root)
                written += r["written"]
                skipped += r["skipped"]
            places = sorted({os.path.dirname(os.path.dirname(p)) for p in written})
            msg = "Installed %d skills (version %s) in %s" % (len(written), version(), ", ".join(places) or "nowhere")
            if skipped:
                msg += "; left %d of yours alone" % len(skipped)
            self.report({"INFO"}, msg)
            return {"FINISHED"}

    class CTX_Preferences(bpy.types.AddonPreferences):
        bl_idname = __package__

        skills_agents: BoolProperty(name="Other agents (Codex, Gemini CLI, Cursor ...)", default=True,
                                    description="~/.agents/skills")
        skills_claude: BoolProperty(name="Claude Code", default=False,
                                    description="~/.claude/skills (not needed if you use the Claude plugin)")
        skills_custom: BoolProperty(name="Another folder", default=False,
                                    description="Any folder an agent reads skills from, e.g. a project's .agents/skills")
        skills_custom_dir: StringProperty(name="Folder", subtype="DIR_PATH",
                                          description="Each skill goes in its own ctx-<name> folder inside this one")

        def draw(self, context):
            col = self.layout.column()
            col.label(text="Agent skills: let a coding agent run the build pipeline on this Blender.")
            for w in ("agents", "claude"):
                row = col.row()
                row.prop(self, "skills_" + w)
                row.label(text=_status(w, None))
            row = col.row()
            row.prop(self, "skills_custom")
            if self.skills_custom and self.skills_custom_dir.strip():
                row.label(text=_status("custom", bpy.path.abspath(self.skills_custom_dir)))
            sub = col.row()
            sub.enabled = self.skills_custom
            sub.prop(self, "skills_custom_dir", text="")
            col.operator(CTX_OT_install_skills.bl_idname, icon="IMPORT")
            col.label(text="This add-on: " + version())
            col.label(text="The agent also needs a Blender MCP add-on to talk to this Blender.")

    CLASSES = (CTX_OT_install_skills, CTX_Preferences)

    def register():
        for c in CLASSES:
            bpy.utils.register_class(c)

    def unregister():
        for c in reversed(CLASSES):
            bpy.utils.unregister_class(c)
