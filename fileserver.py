#!/usr/bin/env python3
"""FileSpace launcher.

Run:
    python fileserver.py
Optional:
    python fileserver.py --root D:\\ --host 0.0.0.0 --port 6789 --env .env
"""

from filespace.app import main


if __name__ == "__main__":
    main()

