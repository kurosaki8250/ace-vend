#!/usr/bin/env python3
"""Start the ACE-Vend web dashboard.

    python run.py                 # http://127.0.0.1:5000
    python run.py --port 8000
    python run.py --mode baseline

Configuration is read from the environment or a ``.env`` file; see
``.env.example`` for every knob.
"""

from ace_vend.api import main

if __name__ == "__main__":
    main()
