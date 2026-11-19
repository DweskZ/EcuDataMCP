"""Stand-in for helpers.supercias_detached_launch in the real-WMI test.

Same command line (ENV_FILE LOG_FILE) and the same duty of deleting the env
file, but it just sleeps instead of running a build.
"""

import sys
import time
from pathlib import Path

Path(sys.argv[1]).unlink(missing_ok=True)
time.sleep(120)
