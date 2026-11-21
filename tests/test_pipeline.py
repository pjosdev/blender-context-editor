"""v0 acceptance tests. Stdlib only; drives headless Blender.

    BLENDER_BIN=/Applications/Blender.app/Contents/MacOS/Blender python3 -m unittest tests.test_pipeline -v

Covers the spec's "v0 is done when" list (except the UI, see tests/ui_smoke.py).
Builds the test scene (tests/make_test_scene.py) in a temp folder first; never touches runs/.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON = os.path.join(ROOT, "addon")
TOOLS = os.path.join(ADDON, "tools")
FIX = os.path.join(ROOT, "tests", "fixtures")
sys.path.insert(0, TOOLS)
import blender_bin as bb  # noqa: E402

BLENDER = bb.blender_bin()
SCENE_DIR = tempfile.mkdtemp(prefix="ctx_scene_")
SCENE = os.path.join(SCENE_DIR, "ship_blockout.blend")


def blender(*args, env=None):
    p = subprocess.run([BLENDER, "-b", "--factory-startup"] + list(args), stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", env=env)
    return p.returncode, p.stdout


def py(*args, env=None):
    p = subprocess.run([sys.executable] + list(args), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       text=True, encoding="utf-8", errors="replace", env=env, cwd=ROOT)
    return p.returncode, p.stdout


def setUpModule():
    code, out = blender("--python-exit-code", "1", "--python", os.path.join(ROOT, "tests", "make_test_scene.py"),
                        "--", SCENE)
    assert code == 0 and os.path.isfile(SCENE), out[-3000:]


def tearDownModule():
    shutil.rmtree(SCENE_DIR, ignore_errors=True)


# ---------------------------------------------------------------- mini JSON Schema check

def validate(inst, schema, root, path="$"):
    errs = []
    if "$ref" in schema:
        schema = root["$defs"][schema["$ref"].split("/")[-1]]
    t = schema.get("type")
    types = {"object": dict, "array": list, "string": str, "integer": int, "number": (int, float),
             "null": type(None), "boolean": bool}
    if t:
        ok = any(isinstance(inst, types[x]) and not (x in ("integer", "number") and isinstance(inst, bool))
                 for x in (t if isinstance(t, list) else [t]))
        if not ok:
            return ["%s: expected %s" % (path, t)]
    if "const" in schema and inst != schema["const"]:
        errs.append("%s: expected %r" % (path, schema["const"]))
    if "enum" in schema and inst not in schema["enum"]:
        errs.append("%s: %r not in %s" % (path, inst, schema["enum"]))
    if "pattern" in schema and isinstance(inst, str) and not re.search(schema["pattern"], inst):
        errs.append("%s: %r doesn't match %s" % (path, inst, schema["pattern"]))
    if isinstance(inst, dict):
        for k in schema.get("required", []):
            if k not in inst:
                errs.append("%s: missing %s" % (path, k))
        for k, sub in schema.get("properties", {}).items():
            if k in inst:
                errs += validate(inst[k], sub, root, path + "." + k)
    if isinstance(inst, list) and "items" in schema:
        for i, item in enumerate(inst):
            errs += validate(item, schema["items"], root, "%s[%d]" % (path, i))
    return errs


class Pipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="ctx_test_")
        cls.blend = os.path.join(cls.tmp, "ship_blockout.blend")
        shutil.copy2(SCENE, cls.blend)
        cls.mtime = os.path.getmtime(cls.blend)
        env = dict(os.environ, CTX_RUNS_DIR=os.path.join(cls.tmp, "runs"))
        code, out = blender(cls.blend, "--python-exit-code", "1", "--python", os.path.join(TOOLS, "export_headless.py"),
                            env=env)
        m = re.search(r"CTX_RUN (.+)", out)
        assert code == 0 and m, out[-2000:]
        cls.rundir = m.group(1).strip()
        with open(os.path.join(cls.rundir, "context.json")) as f:
            cls.ctx = json.load(f)
        cls.by_coll = {s["collection"]: s for s in cls.ctx["sections"]}
        # Install the generic test build for every section.
        os.makedirs(os.path.join(cls.rundir, "scripts"))
        for s in cls.ctx["sections"]:
            shutil.copy2(os.path.join(FIX, "build_panels.py"),
                         os.path.join(cls.rundir, "scripts", "%02d_%s.py" % (s["order"], s["id"])))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def script(self, coll):
        s = self.by_coll[coll]
        return os.path.join(self.rundir, "scripts", "%02d_%s.py" % (s["order"], s["id"]))

    def dump(self, blend):
        out = os.path.join(self.tmp, "dump_%d.json" % abs(hash(blend)))
        code, log = blender(blend, "--python-exit-code", "1", "--python", os.path.join(ROOT, "tests", "bl_dump.py"), "--", out)
        self.assertEqual(code, 0, log[-2000:])
        with open(out) as f:
            return json.load(f)

    # -------------------------------------------------------------- tests (run in name order)

    def test_01_export_validates(self):
        with open(os.path.join(ROOT, "schema", "context.schema.json")) as f:
            schema = json.load(f)
        self.assertEqual(validate(self.ctx, schema, schema), [])
        self.assertEqual(len(self.ctx["sections"]), 4)
        cockpit = self.by_coll["COCKPIT"]
        self.assertEqual([g["label"] for g in cockpit["groups"]], ["console plastic"])
        g = cockpit["groups"][0]
        self.assertEqual(len(g["refs"]), 1)
        self.assertEqual([n["name"] for n in g["notes"]], ["plastic notes"])
        self.assertEqual([n["name"] for n in cockpit["notes"]], ["cockpit shape"])
        self.assertEqual(cockpit["refs"], [])
        # The console drawing sits in the "console plastic" frame: render + world-space stroke points.
        self.assertEqual([k["object"] for k in g["sketches"]], ["console sketch"])
        k = g["sketches"][0]
        self.assertTrue(os.path.isfile(os.path.join(self.rundir, k["image"])))
        with open(os.path.join(self.rundir, k["strokes"])) as f:
            strokes = json.load(f)
        pts = [p for layer in strokes["layers"] for st in layer["strokes"] for p in st["points"]]
        self.assertEqual(len(pts), 3 * 5 + 7 * 2)
        self.assertTrue(all(abs(p[2] - 0.33) < 1e-3 for p in pts))
        # A drawing is context, not block-out.
        self.assertNotIn("console sketch", [o["name"] for o in cockpit["objects"]])
        seats = self.by_coll["SEATS"]
        self.assertEqual(seats["parent_id"], self.by_coll["COCKPIT"]["id"])
        for s in self.ctx["sections"]:
            self.assertTrue(os.path.isfile(os.path.join(self.rundir, s["blockout_preview"])), s["title"])
            for r in s["refs"] + [r for g in s["groups"] for r in g["refs"]]:
                self.assertTrue(os.path.isfile(os.path.join(self.rundir, r["file"])))

    def test_02_script_idempotent_and_contained(self):
        for coll in ("COCKPIT", "WING_L", "ENGINES", "SEATS"):
            s = self.by_coll[coll]
            code, out = blender(os.path.join(self.rundir, "base.blend"), "--python-exit-code", "1",
                                "--python", os.path.join(TOOLS, "run_script.py"), "--",
                                "--step", s["id"], self.script(coll), "--check-idempotent",
                                "--touched-dir", os.path.join(self.rundir, "touched"))
            self.assertEqual(code, 0, out[-2000:])
            with open(os.path.join(self.rundir, "touched", s["id"] + ".json")) as f:
                t = json.load(f)
            self.assertTrue(t["idempotent"])
            self.assertEqual(t["violations"], [])
            self.assertTrue(all(k.split("/", 1)[1].startswith(s["prefix"]) for k in t["created"]))

    def test_03_violation_detected(self):
        s = self.by_coll["WING_L"]
        code, out = blender(os.path.join(self.rundir, "base.blend"), "--python-exit-code", "1",
                            "--python", os.path.join(TOOLS, "run_script.py"), "--",
                            "--step", s["id"], os.path.join(FIX, "touch_hull.py"))
        self.assertEqual(code, 2, out[-2000:])
        self.assertIn("CTX_VIOLATION %s objects/hull_body" % s["id"], out)

    def test_04_child_copy_includes_parent(self):
        seats = self.by_coll["SEATS"]
        env = dict(os.environ, BLENDER_BIN=BLENDER)
        code, out = py(os.path.join(TOOLS, "make_copies.py"), self.rundir, seats["id"], env=env)
        self.assertEqual(code, 0, out)
        d = self.dump(os.path.join(self.rundir, "work", seats["id"], "work.blend"))
        cockpit_prefix = self.by_coll["COCKPIT"]["prefix"]
        self.assertTrue(any(k.startswith("objects/" + cockpit_prefix) for k in d["snap"]),
                        "child copy lacks the parent's build")

    def test_05_merge_all_no_conflicts(self):
        env = dict(os.environ, BLENDER_BIN=BLENDER)
        for s in self.ctx["sections"]:
            code, out = py(os.path.join(TOOLS, "decide.py"), self.rundir, s["id"], "keep", env=env)
            self.assertEqual(code, 0, out)
        code, out = py(os.path.join(TOOLS, "merge.py"), self.rundir, env=env)
        self.assertEqual(code, 0, out)
        self.assertTrue(os.path.isfile(os.path.join(self.rundir, "build.blend")))
        self.assertTrue(os.path.isfile(os.path.join(self.rundir, "previews", "build.png")))
        with open(os.path.join(self.rundir, "build_report.json")) as f:
            rep = json.load(f)
        self.assertEqual(rep["conflicts"], [])
        self.assertTrue(all(not st["violations"] for st in rep["steps"]))

    def test_06_rerun_changes_only_that_section(self):
        env = dict(os.environ, BLENDER_BIN=BLENDER)
        before = self.dump(os.path.join(self.rundir, "build.blend"))
        wing = self.by_coll["WING_L"]
        py(os.path.join(TOOLS, "decide.py"), self.rundir, wing["id"], "redo", "--note", "bluer", env=env)
        self.assertTrue(os.path.isfile(os.path.join(self.rundir, "feedback", wing["id"] + ".md")))
        shutil.copy2(os.path.join(FIX, "build_panels_v2.py"), self.script("WING_L"))
        py(os.path.join(TOOLS, "decide.py"), self.rundir, wing["id"], "keep", env=env)
        code, out = py(os.path.join(TOOLS, "merge.py"), self.rundir, env=env)
        self.assertEqual(code, 0, out)
        after = self.dump(os.path.join(self.rundir, "build.blend"))
        changed = {k for k in set(before["snap"]) | set(after["snap"])
                   if before["snap"].get(k) != after["snap"].get(k)}
        self.assertTrue(changed, "rerun changed nothing")
        wing_owned = set(after["owned"][wing["id"]]) | set(before["owned"][wing["id"]])
        self.assertEqual(sorted(changed - wing_owned), [])

    def test_07_conflict_stops_merge(self):
        env = dict(os.environ, BLENDER_BIN=BLENDER, CTX_OTHER_PREFIX=self.by_coll["COCKPIT"]["prefix"])
        shutil.copy2(os.path.join(FIX, "grab_other.py"), self.script("ENGINES"))
        code, out = py(os.path.join(TOOLS, "merge.py"), self.rundir, env=env)
        self.assertNotEqual(code, 0)
        self.assertIn("CONFLICT: materials/%spaint was touched by both" % self.by_coll["COCKPIT"]["prefix"], out)
        shutil.copy2(os.path.join(FIX, "build_panels.py"), self.script("ENGINES"))

    def test_08_apply_backs_up_and_applies(self):
        env = dict(os.environ, BLENDER_BIN=BLENDER)
        self.assertEqual(os.path.getmtime(self.blend), self.mtime, "a run step wrote the original file")
        code, out = py(os.path.join(TOOLS, "apply.py"), self.rundir, "--target", self.blend, env=env)
        self.assertEqual(code, 0, out)
        backups = [f for f in os.listdir(self.tmp) if ".ctx-backup-" in f]
        self.assertEqual(len(backups), 1)
        d = self.dump(self.blend)
        self.assertTrue(any(k.startswith("objects/" + self.by_coll["COCKPIT"]["prefix"]) for k in d["snap"]))
        self.assertIn("node_groups/Context", d["snap"], "the board was lost on apply")
        # Applying twice converges (idempotent on the artist's file).
        code, out = py(os.path.join(TOOLS, "apply.py"), self.rundir, "--target", self.blend, env=env)
        self.assertEqual(code, 0, out)
        d2 = self.dump(self.blend)
        self.assertEqual(sorted(k for k in set(d["snap"]) | set(d2["snap"]) if d["snap"].get(k) != d2["snap"].get(k)), [])


SCRAMBLE = """
import bpy
for i, o in enumerate(sorted(bpy.data.objects, key=lambda o: o.name)):
    if o.type == "MESH":
        o.name = "Cube.%03d" % i
bpy.ops.wm.save_mainfile()
"""

CHECK_ORGANIZED = """
import bpy, json, sys
sys.path.insert(0, sys.argv[-1])
import scene_model as sm
out = {o.name: [sm.collection_path(c) for c in o.users_collection] for o in bpy.data.objects}
print("CTX_DUMP " + json.dumps(out))
"""


class Organize(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="ctx_org_")
        cls.blend = os.path.join(cls.tmp, "junk.blend")
        shutil.copy2(SCENE, cls.blend)
        code, out = blender(cls.blend, "--python-expr", SCRAMBLE)
        assert code == 0, out[-2000:]
        code, out = blender(cls.blend, "--python-exit-code", "1", "--python", os.path.join(TOOLS, "organize.py"),
                            "--", "inspect", cls.tmp)
        m = re.search(r"CTX_ORGANIZE (.+)", out)
        assert code == 0 and m, out[-2000:]
        cls.dir = json.loads(m.group(1))["dir"]
        with open(os.path.join(cls.dir, "scene.json")) as f:
            cls.scene = {o["name"]: o for o in json.load(f)["objects"]}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def by(self, coll, n=0):
        return sorted(k for k, o in self.scene.items() if o["collections"] == ["SHIP/" + coll])[n]

    def run_plan(self, plan, *flags):
        path = os.path.join(self.dir, "organize.json")
        with open(path, "w") as f:
            json.dump(plan, f)
        code, out = blender(self.blend, "--python", os.path.join(TOOLS, "organize.py"), "--", "apply", path, *flags)
        m = re.search(r"CTX_ORGANIZE (.+)", out)
        self.assertTrue(m, out[-2000:])
        return code, json.loads(m.group(1))

    def test_01_inspect(self):
        self.assertTrue(self.scene["CTX_CAM_SEATS"]["locked"])
        self.assertEqual(self.scene[self.by("COCKPIT/SEATS")]["section"], "SEATS")
        self.assertEqual(self.scene[self.by("HULL")]["section"], None)

    def test_02_bad_plan_changes_nothing(self):
        before = os.path.getmtime(self.blend)
        code, r = self.run_plan({"objects": [
            {"name": self.by("ENGINES"), "collection": ["SHIP", "HULL"]},          # leaves its section
            {"name": "CTX_CAM_SEATS", "new_name": "seat_cam"},                     # pipeline object
            {"name": self.by("HULL", 0), "new_name": self.by("HULL", 1)},          # name taken
            {"name": self.by("COCKPIT"), "collection": ["COCKPIT"]},              # exists elsewhere
            {"name": "nope"},
        ]}, "--save")
        self.assertEqual(code, 2)
        self.assertEqual(len(r["errors"]), 5, r["errors"])
        self.assertEqual(os.path.getmtime(self.blend), before)

    def test_03_apply(self):
        a, b = self.by("ENGINES", 0), self.by("ENGINES", 1)
        hull = self.by("HULL", 0)
        code, r = self.run_plan({"objects": [
            {"name": a, "new_name": b},                     # swap two names
            {"name": b, "new_name": a},
            {"name": hull, "new_name": "hull_spine", "collection": ["SHIP", "HULL", "Spine"]},
            {"name": self.by("COCKPIT/SEATS"), "new_name": "seat_left", "collection": ["SHIP", "COCKPIT", "SEATS", "Frames"]},
        ]}, "--save")
        self.assertEqual(code, 0, r)
        self.assertEqual(len(r["renamed"]), 4)
        self.assertEqual(sorted(r["created_collections"]), ["SHIP/COCKPIT/SEATS/Frames", "SHIP/HULL/Spine"])
        self.assertEqual(len([f for f in os.listdir(self.tmp) if ".ctx-backup-" in f]), 1)
        code, out = blender(self.blend, "--python-expr", CHECK_ORGANIZED, "--", ADDON)
        d = json.loads(re.search(r"CTX_DUMP (.+)", out).group(1))
        self.assertEqual(d["hull_spine"], ["SHIP/HULL/Spine"])
        self.assertEqual(d["seat_left"], ["SHIP/COCKPIT/SEATS/Frames"])
        self.assertIn(a, d)
        self.assertIn(b, d)
        self.assertFalse(any(k.startswith("__ctx_organize") or re.search(r"\.\d{3}$", k) and k not in self.scene
                             for k in d), d)


class Addon(unittest.TestCase):
    def test_install_and_round_trip(self):
        tmp = tempfile.mkdtemp(prefix="ctx_addon_")
        try:
            code, out = py(os.path.join(TOOLS, "build_addon.py"), tmp)
            self.assertEqual(code, 0, out)
            home = os.path.join(tmp, "home")  # the skills button's ~ ; starts empty
            os.makedirs(home)
            env = dict(os.environ, BLENDER_USER_RESOURCES=os.path.join(tmp, "userres"), CTX_TMP=tmp,
                       HOME=home, USERPROFILE=home)
            code, out = blender("--python-exit-code", "1", "--python", os.path.join(ROOT, "tests", "bl_addon_roundtrip.py"),
                                "--", os.path.join(tmp, "context_editor.zip"), env=env)
            self.assertEqual(code, 0, out[-3000:])
            self.assertIn("CTX_ROUNDTRIP_SAVED", out)
            snap = json.loads(re.search(r"CTX_SNAPSHOT (.+)", out).group(1))
            # the installed add-on's tools run on Blender's own Python
            p = subprocess.run([snap["python"], os.path.join(snap["addon"], "tools", "wait_previews.py"), snap["run_dir"]],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                               errors="replace")
            self.assertEqual(p.returncode, 0, p.stdout[-2000:])
            p = subprocess.run([snap["python"], os.path.join(snap["addon"], "tools", "decide.py"), snap["run_dir"]],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                               errors="replace")
            self.assertEqual(p.returncode, 0, p.stdout)
            self.assertIn("Part", p.stdout)
            resaved = os.path.join(tmp, "resaved.blend")
            code, out = blender(os.path.join(tmp, "board.blend"), "--python-expr",
                                "import bpy; bpy.ops.wm.save_as_mainfile(filepath=%r)" % resaved)
            self.assertEqual(code, 0, out[-2000:])
            code, out = blender(resaved, "--python-exit-code", "1", "--python",
                                os.path.join(ROOT, "tests", "bl_addon_roundtrip.py"), "--", "--check", env=env)
            self.assertEqual(code, 0, out[-3000:])
            self.assertIn("CTX_ROUNDTRIP_OK", out)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
