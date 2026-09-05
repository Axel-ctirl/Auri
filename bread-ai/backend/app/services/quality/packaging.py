"""Do the install instructions match the code?

A model that writes `from dotenv import load_dotenv` and then tells you to run
`pip install disnake` has produced an answer that fails on the first line. The
mistake is in the gap between the prose and the code, so neither a name check
nor a framework rule sees it: the import resolves fine, and the install command
is not Python at all.

The mapping from an import name to the thing you install is not mechanical, so
the common cases are written down. Anything not on the list is left alone rather
than guessed at.
"""

from __future__ import annotations

import ast
import re
import sys

from .api_check import Finding

# Import name -> what you actually pip install. Only the ones that differ, plus
# the ones common enough that a wrong guess would be expensive.
DISTRIBUTIONS = {
    "aiohttp": "aiohttp",
    "aiosqlite": "aiosqlite",
    "attr": "attrs",
    "bs4": "beautifulsoup4",
    "cv2": "opencv-python",
    "discord": "discord.py",
    "disnake": "disnake",
    "dotenv": "python-dotenv",
    "fastapi": "fastapi",
    "fitz": "PyMuPDF",
    "google": "google-api-python-client",
    "httpx": "httpx",
    "jwt": "PyJWT",
    "nextcord": "nextcord",
    "numpy": "numpy",
    "pandas": "pandas",
    "PIL": "Pillow",
    "psycopg2": "psycopg2-binary",
    "pydantic": "pydantic",
    "pytest": "pytest",
    "redis": "redis",
    "requests": "requests",
    "serial": "pyserial",
    "sklearn": "scikit-learn",
    "sqlalchemy": "SQLAlchemy",
    "torch": "torch",
    "uvicorn": "uvicorn",
    "yaml": "PyYAML",
}

INSTALL_LINE = re.compile(
    r"(?:pip3?|python3?\s+-m\s+pip|uv\s+pip)\s+install\s+(?P<packages>[^\n#]+)",
    re.IGNORECASE,
)
# Strip the flags and version pins off a requirement so `disnake>=2.10` matches.
REQUIREMENT = re.compile(r"^[A-Za-z0-9._-]+")


def installed_packages(answer: str) -> set[str]:
    """Every distribution the answer tells the reader to install."""

    names: set[str] = set()
    for match in INSTALL_LINE.finditer(answer or ""):
        for token in match.group("packages").split():
            token = token.strip("\"'`,")
            if token.startswith("-"):
                continue
            requirement = REQUIREMENT.match(token)
            if requirement:
                names.add(requirement.group(0).lower().replace("_", "-"))
    return names


def imported_modules(code: str) -> dict[str, int]:
    """Top-level module names the code imports, with the line each appears on."""

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {}

    modules: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.setdefault(alias.name.split(".")[0], node.lineno)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.setdefault(node.module.split(".")[0], node.lineno)
    return modules


def check_install_instructions(answer: str, code: str) -> list[Finding]:
    """Third-party imports the answer's own install command leaves out."""

    declared = installed_packages(answer)
    if not declared:
        # No install instructions at all is a different complaint, and not one
        # this check is entitled to make: the reader may already have the deps.
        return []

    findings: list[Finding] = []
    for module, line in sorted(imported_modules(code).items(), key=lambda item: item[1]):
        if module in sys.stdlib_module_names or module.startswith("_"):
            continue
        distribution = DISTRIBUTIONS.get(module)
        if distribution is None:
            # Not on the list, so the install name is unknown. Guessing here
            # would report a fact that is only a hunch.
            continue
        if distribution.lower().replace("_", "-") in declared:
            continue
        findings.append(
            Finding(
                kind="packaging",
                symbol=module,
                line=line,
                message=(
                    f"the answer imports `{module}` but its install command does not "
                    f"install it: add `{distribution}`"
                ),
            )
        )
    return findings
