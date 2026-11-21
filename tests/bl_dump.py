"""Dump {key: fingerprint} + owned keys per section of the opened .blend to a JSON file."""
import json, os, sys
import bpy
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "addon", "tools"))
import fingerprint as fp
out = sys.argv[sys.argv.index("--") + 1]
import scene_model as sm
data = {"snap": fp.snapshot(), "owned": {sid: sorted(fp.owned_keys(sid)) for sid in sm.section_collections()}}
with open(out, "w") as f:
    json.dump(data, f)
