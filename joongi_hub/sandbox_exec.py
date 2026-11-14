"""Trusted helper: install restrictions, then exec the untrusted program."""

import json
import os
import sys
from pathlib import Path


def main():
    try:
        policy = json.loads(Path(sys.argv[1]).read_bytes())
        from joongi_hub.linux_sandbox import enforce

        os.chdir(policy["scratch"])
        enforce(policy)
        environment = {
            **policy["environment"],
            "HOME": policy["scratch"],
            "TMPDIR": policy["scratch"],
            "TMP": policy["scratch"],
            "TEMP": policy["scratch"],
        }
        os.execve(policy["command"][0], policy["command"], environment)
    except Exception:
        print("MCP sandbox enforcement failed; unrestricted execution is disabled", file=sys.stderr)
        return 126


if __name__ == "__main__":
    raise SystemExit(main())
