# Python Core Standard

## Overview

Standards for Python development including project structure, naming conventions, and coding style.

## Principles

1. **PEP Compliance** — Follow PEP-8, PEP-621, and other Python Enhancement Proposals
2. **Modern Tooling** — Use fast, modern tools (uv, Ruff) over legacy alternatives
3. **Type Safety** — Leverage type hints for better code quality
4. **Reproducibility** — Ensure consistent environments across machines
5. **Simplicity** — Favour simple scripts and lightweight modules over heavy package architecture

---

## Project Structure

### Recommended Layout (Scripts)

For repositories primarily containing utility scripts (rather than distributable packages), use a flat layout:

```
scripts/
├── .env                    # Configuration (gitignored if sensitive)
├── .python-version         # Python version pin
├── pyproject.toml          # Dependencies and tool config
├── backup_sd_card.py
├── sync_samples.py
├── lib/                    # Shared modules (if needed)
│   ├── __init__.py
│   └── xml_helpers.py
└── tests/
    ├── conftest.py
    └── test_xml_helpers.py
```

### Package Layout (Informational)

The scripts layout above is the primary recommendation for this repository. For distributable packages or larger applications, the `src/` layout is an alternative:

```
project/
├── src/
│   └── my_project/
│       ├── __init__.py
│       ├── main.py
│       └── utils/
│           ├── __init__.py
│           └── helpers.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   └── test_main.py
├── pyproject.toml
├── README.md
└── .python-version
```

### Python Version File

Create `.python-version` to specify Python version:

```
3.12
```

---

## Script Patterns

### Entry Point

All scripts **MUST** use the `if __name__ == "__main__"` guard:

```python
import argparse
import sys


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Brief description of the script")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    args = parser.parse_args(argv)

    # Script logic here


if __name__ == "__main__":
    main()
```

**Rationale:** Separating `main()` from the guard enables testing and reuse. The `argv` parameter allows tests to pass arguments directly.

### Configuration from `.env`

Scripts read configuration from `scripts/.env`. Use `python-dotenv` or parse manually:

```python
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
sd_card_path = os.environ.get("SD_CARD_PATH")
```

### Path Operations

Use `pathlib.Path` for **all** file and directory operations. Do not use `os.path`.

```python
from pathlib import Path

deluge_dir = Path("DELUGE")
sample_path = deluge_dir / "SAMPLES" / "DRUMS" / "Kick.wav"

if sample_path.exists():
    content = sample_path.read_text()

for xml_file in deluge_dir.glob("KITS/**/*.XML"):
    process(xml_file)
```

### XML Handling

Use `lxml` for XML parsing and manipulation. It is significantly faster than the standard library `xml.etree` module and provides better XPath support.

```python
from lxml import etree

tree = etree.parse(str(xml_path))
root = tree.getroot()
file_names = root.xpath("//fileName/text()")
```

---

## Project Configuration

### pyproject.toml (PEP-621)

All Python projects **MUST** use `pyproject.toml` for project metadata and dependency management.

#### Scripts Project

For a scripts-focused project (no build/distribution needed):

```toml
[project]
name = "deluge-scripts"
version = "0.1.0"
description = "Management scripts for a Deluge SD card"
requires-python = ">=3.11"
dependencies = [
    "lxml>=5.0.0",
]

[project.optional-dependencies]
dev = [
    "ruff>=0.1.0",
    "mypy>=1.0.0",
    "pytest>=7.0.0",
]
```

> **Note:** A `[build-system]` section is not required for scripts-only projects managed with `uv`.

#### Distributable Package

For projects that will be built and distributed:

```toml
[project]
name = "my-project"
version = "0.1.0"
description = "A brief description of the project"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "requests>=2.28.0",
]

[project.optional-dependencies]
dev = [
    "ruff>=0.1.0",
    "mypy>=1.0.0",
    "pytest>=7.0.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

---

## Naming Conventions

| Type | Convention | Example |
|------|------------|---------|
| Variables | snake_case | `user_name`, `is_active` |
| Functions | snake_case | `get_user_by_id`, `validate_input` |
| Classes | PascalCase | `UserService`, `HttpClient` |
| Constants | UPPER_SNAKE_CASE | `MAX_RETRIES`, `API_URL` |
| Modules | snake_case | `user_service.py`, `api_client.py` |
| Packages | lowercase | `mypackage`, `utilities` |

---

## Type Hints

Type hints are **mandatory** for all Python code.

### Basic Types

```python
name: str = "Alice"
count: int = 42
is_active: bool = True

def greet(name: str) -> str:
    return f"Hello, {name}"

def log_message(message: str) -> None:
    print(message)
```

### Collection Types (Python 3.9+)

```python
def process_items(items: list[str]) -> dict[str, int]:
    return {item: len(item) for item in items}

names: set[str] = {"alice", "bob"}
mapping: dict[str, list[int]] = {"numbers": [1, 2, 3]}
```

### Optional and Union Types (Python 3.10+)

```python
def find_user(user_id: str) -> User | None:
    ...

def parse_value(value: str) -> int | float | None:
    ...
```

### When to Use `Any`

Avoid `Any` when possible. Valid uses:

```python
# Valid: Truly dynamic data from external sources
def parse_json_response(response: str) -> dict[str, Any]:
    ...
```

---

## Docstrings (Google Style)

```python
def find_broken_references(kit_path: Path, samples_dir: Path) -> list[str]:
    """Find broken sample references in a kit XML.

    Args:
        kit_path: Path to the kit XML file.
        samples_dir: Root directory containing audio samples.

    Returns:
        A list of sample file paths that could not be found on disk.

    Raises:
        FileNotFoundError: If the kit XML does not exist.
    """
    ...
```

---

## Simplicity

Python-specific guidance extending the general simplicity rules in the implementation process standard.

### Data Modelling

- Prefer `str`, `list`, `dict`, `tuple`, `NamedTuple` over single-field dataclasses
- Only create a `dataclass` when there are 3+ fields or the type has behaviour beyond data storage

### Testing

- Do not test stdlib behaviour (e.g. that `sorted()` sorts, that `Path.exists()` works)

---

## Import Organisation

Ruff handles import sorting automatically. Manual organisation:

```python
# Standard library
import os
from pathlib import Path

# Third-party
from lxml import etree

# Local
from lib.xml_helpers import parse_kit
```
