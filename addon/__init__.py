bl_info = {
    "name": "Context Editor",
    "author": "pjos",
    "version": (0, 4, 3),
    "blender": (5, 2, 0),
    "location": "Node Editor > Context Editor; 3D View > Sidebar > Context",
    "description": "A reference board linked to scene collections, exported for a multi-agent build pipeline",
    "category": "Node",
}

from . import agent_skills, export, file_handler, scene_model, tree, ui  # noqa: E402,F401

_MODULES = (tree, ui, file_handler, agent_skills)


def register():
    for m in _MODULES:
        m.register()


def unregister():
    for m in reversed(_MODULES):
        m.unregister()
