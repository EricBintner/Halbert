import json, os, platform, shlex, shutil, subprocess, sys
from typing import List, Optional

def _seatbelt_str(path): return json.dumps(path)

src = open(os.path.join(os.path.dirname(__file__), "new_seatbelt.py")).read()
ns = {"json": json, "os": os, "platform": platform, "shlex": shlex,
      "shutil": shutil, "Optional": Optional, "List": List,
      "_seatbelt_str": _seatbelt_str}
exec(compile(src, "new_seatbelt.py", "exec"), ns)

Sandbox = ns["Sandbox"]
s = Sandbox()
wrapped = s.wrap_command(
    sys.argv[1],
    writable_paths=["/tmp/sbxw"],          # deliberately the UNRESOLVED spelling
    read_paths=["/tmp/sbxr"],
    allow_network=(os.environ.get("NET") == "1"),
)
if os.environ.get("SHOW") == "1":
    print(wrapped.split("-p ")[1].rsplit(" /bin/sh", 1)[0].strip("'"))
    sys.exit(0)
sys.exit(subprocess.call(["/bin/sh", "-c", wrapped]))
