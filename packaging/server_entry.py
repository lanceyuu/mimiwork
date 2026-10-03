"""PyInstaller entry point for the bundled desktop sidecar server.

Thin wrapper so PyInstaller has a concrete script to analyze (the console_script
`openworker-server` is generated metadata, not a file). Runs the same `main()`.

The same binary also serves as the analysis kernel: a frozen app has no interpreter to run
`python -m`, so the kernel relaunches this executable with a flag, dispatched here before the
server's imports are paid for.
"""

import sys

from coworker.tools.analysis._kernel_child import ENTRY_FLAG

if __name__ == "__main__":
    if sys.argv[1:2] == [ENTRY_FLAG]:
        from coworker.tools.analysis._kernel_child import main as kernel_main

        sys.argv = [sys.argv[0], *sys.argv[2:]]
        kernel_main()
    else:
        from coworker.server.run import main

        main()
