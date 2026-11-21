"""Wait for a run's preview renders (block-out and sketch) to finish. Stdlib only.

    python3 tools/wait_previews.py runs/<run> [--timeout 900]

Exit 0 when previews/done.json exists and every listed image is on disk.
Exit 1 if the render process died first or images are missing (prints the end of render.log).
"""

import json
import os
import sys
import time


def _alive(pid):
    if os.name == "nt":
        # os.kill(pid, 0) on Windows terminates the process; ask the OS instead.
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
        k32.CloseHandle(h)
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def main(argv):
    if not argv:
        sys.exit(__doc__)
    run_dir = os.path.abspath(argv[0])
    timeout = float(argv[argv.index("--timeout") + 1]) if "--timeout" in argv else 900.0
    prev = os.path.join(run_dir, "previews")
    done = os.path.join(prev, "done.json")
    log = os.path.join(prev, "blockout", "render.log")
    pid_file = os.path.join(prev, "render.pid")
    if not os.path.isfile(pid_file):
        print("CTX_PREVIEWS_OK nothing to render")
        return 0
    pid = int(open(pid_file).read())
    start = time.time()
    def crashed():
        # The renderer is a child of the artist's Blender, so a finished one can linger as a zombie;
        # a script failure shows in the log.
        if not os.path.isfile(log):
            return False
        text = open(log, errors="replace").read()
        return "Traceback" in text or "Error: script failed" in text

    while not os.path.isfile(done):
        if not _alive(pid) or crashed() or time.time() - start > timeout:
            if os.path.isfile(done):
                break
            why = "render script failed" if crashed() else "timed out" if _alive(pid) else \
                "render process ended without finishing"
            print("CTX_PREVIEWS_FAILED", why)
            if os.path.isfile(log):
                print("".join(open(log).readlines()[-30:]))
            return 1
        time.sleep(1.0)
    with open(done) as f:
        d = json.load(f)
    missing = [p for p in d["blockout"] + d["sketch"] if not os.path.isfile(os.path.join(run_dir, p))]
    if missing:
        print("CTX_PREVIEWS_MISSING", missing)
        return 1
    print("CTX_PREVIEWS_OK", len(d["blockout"]), "block-out,", len(d["sketch"]), "sketch")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
