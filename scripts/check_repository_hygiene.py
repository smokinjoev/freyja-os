from __future__ import annotations

import re
import subprocess
import sys
from pathlib import PurePosixPath


FORBIDDEN_PATHS = (
    re.compile(r"(^|/)\.env$"),
    re.compile(r"\.(db|sqlite|sqlite3|log|jsonl)$", re.IGNORECASE),
    re.compile(r"(^|/)(\.venv|__pycache__|\.pytest_cache|signal-cli-data)(/|$)"),
)
SECRET_PATTERNS = {
    "private key": re.compile(r"BEGIN (RSA |OPENSSH |EC |DSA )?PRIVATE KEY"),
    "AWS access key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "GitHub token": re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    "OpenAI-style key": re.compile(r"sk-[A-Za-z0-9_-]{32,}"),
    "Slack token": re.compile(r"xox[baprs]-[A-Za-z0-9-]{20,}"),
}


def tracked_files() -> list[str]:
    result = subprocess.run(["git", "ls-files", "-z"], check=True, capture_output=True)
    return [item.decode() for item in result.stdout.split(b"\0") if item]


def main() -> int:
    failures: list[str] = []
    for filename in tracked_files():
        normalized = str(PurePosixPath(filename))
        if any(pattern.search(normalized) for pattern in FORBIDDEN_PATHS):
            failures.append(f"forbidden tracked runtime path: {normalized}")
            continue
        try:
            content = open(filename, "r", encoding="utf-8").read()
        except (OSError, UnicodeDecodeError):
            continue
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(content):
                failures.append(f"possible {label} in tracked file: {normalized}")
    if failures:
        print("Repository hygiene check failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("Repository hygiene check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
