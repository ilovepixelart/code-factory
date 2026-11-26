"""Run by test_capture_script: 25 captures of one payload through the hook's own function."""

import runpy
import sys

hook = runpy.run_path(sys.argv[1])
for _ in range(25):
    hook["capture"](sys.argv[2].encode(), 1.0, sys.argv[3])
