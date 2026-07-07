#!/usr/bin/env python3
"""
Feed an SSH password + Duo answer to the system `ssh` via SSH_ASKPASS, so auth can
come from the GUI instead of a terminal prompt.

ssh runs $SSH_ASKPASS once per prompt with the prompt text as argv[1]; the helper
returns the Duo answer for a passcode/Duo prompt, else the password. Secrets are
passed only through the ssh subprocess environment and never stored. Localhost use.
"""

from __future__ import annotations

import os
import stat
import tempfile

_ASKPASS = (
    "#!/usr/bin/env python3\n"
    "import os, sys\n"
    "p = (sys.argv[1] if len(sys.argv) > 1 else '').lower()\n"
    "duo = any(w in p for w in ('passcode', 'duo', 'option', 'two-factor'))\n"
    "sys.stdout.write(os.environ.get('MS_DUO' if duo else 'MS_PW', ''))\n"
)


def askpass_env(password: str | None, duo: str | None = None):
    """Return (env, cleanup): an environment that makes ssh answer prompts from
    `password`/`duo` with no terminal interaction. `duo` defaults to "1" (Duo
    Push). Call cleanup() when done to remove the temp helper."""
    fd, path = tempfile.mkstemp(prefix="ms-askpass-", suffix=".py")
    with os.fdopen(fd, "w") as f:
        f.write(_ASKPASS)
    os.chmod(path, stat.S_IRWXU)
    env = dict(os.environ)
    env.update(
        {
            "SSH_ASKPASS": path,
            "SSH_ASKPASS_REQUIRE": "force",  # use askpass even with a tty (OpenSSH ≥8.4)
            # subprocess env values must be strings: a key-based + Duo login has no
            # password, so coerce None → "" (else Popen raises "expected str ... not
            # NoneType"). The Duo prompt is still answered from MS_DUO.
            "MS_PW": password or "",
            "MS_DUO": duo or "1",
            "DISPLAY": env.get("DISPLAY", ":0"),
        }
    )
    return env, (lambda: os.path.exists(path) and os.unlink(path))
