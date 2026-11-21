"""Locate Blender: from the run folder, else $BLENDER_BIN. Stdlib only."""

import json
import os
import subprocess
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))


def blender_bin(run_dir=None):
    """The Blender that made the run: context.json "blender_bin" (read from the artist's open Blender
    over the MCP at snapshot time). $BLENDER_BIN only when there is no run folder (tests, example)."""
    if run_dir:
        p = os.path.join(run_dir, "context.json")
        if os.path.isfile(p):
            with open(p) as f:
                b = json.load(f).get("blender_bin")
            if b and os.path.isfile(b):
                return b
            sys.exit("context.json in %s has no usable blender_bin (%r)" % (run_dir, b))
    b = os.environ.get("BLENDER_BIN")
    if not b:
        sys.exit("No run folder and BLENDER_BIN is not set.")
    if not os.path.isfile(b):
        sys.exit("BLENDER_BIN=%s does not exist" % b)
    return b


def run_blender(blend, script, script_args, log_path=None, run_dir=None):
    """Headless, factory-startup Blender run. Returns (returncode, output)."""
    cmd = [blender_bin(run_dir), "-b", "--factory-startup", blend, "--python-exit-code", "1",
           "--python", script, "--"] + list(script_args)
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    if log_path:
        os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(p.stdout)
    return p.returncode, p.stdout
