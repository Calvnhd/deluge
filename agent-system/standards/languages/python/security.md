# Python Security Standard

## Overview

Security requirements for Python code.

---

## Prohibited Practices

| Practice | Reason | Alternative |
|----------|--------|-------------|
| `eval()` / `exec()` | Code injection risk | Use `ast.literal_eval()` or proper parsing |
| `pickle` with untrusted data | Arbitrary code execution | Use JSON or validated serialisation |
| Hardcoded secrets | Credential exposure | Use environment variables |
| `shell=True` in subprocess | Command injection | Use argument lists |
| `assert` for validation | Disabled with `-O` flag | Use proper validation |

---

## Secure Practices

### Environment Variables for Secrets

```python
import os

api_key = os.environ.get("API_KEY")
if not api_key:
    raise ValueError("API_KEY environment variable required")
```

### Safe Subprocess Calls

```python
import subprocess
from pathlib import Path

# Use argument lists, not shell=True
result = subprocess.run(
    ["ls", "-la", str(Path.home())],
    capture_output=True,
    text=True,
    check=True,
)
```

### Input Validation with Pydantic

```python
from pydantic import BaseModel, Field

class UserInput(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    email: str = Field(..., pattern=r"^[\w\.-]+@[\w\.-]+\.\w+$")
```

### Safe JSON Parsing

```python
import ast

# For literal Python structures
data = ast.literal_eval(user_input)

# For JSON data
import json
data = json.loads(user_input)
```

### Safe XML Parsing

XML parsers are vulnerable to entity expansion attacks (XXE) by default. When parsing XML from external or untrusted sources, disable entity resolution:

```python
from lxml import etree

# Create a parser that disables network access and entity resolution
parser = etree.XMLParser(resolve_entities=False, no_network=True)
tree = etree.parse(str(xml_path), parser)
```

For XML files originating from the local `DELUGE/` directory, the standard `etree.parse()` is acceptable since the files are under version control. Use the safe parser when processing XML from external sources (e.g. community presets, downloads).

### Path Validation

When scripts accept file paths as input, validate that resolved paths stay within expected directories to prevent path traversal:

```python
from pathlib import Path

def validate_path(user_path: Path, allowed_root: Path) -> Path:
    """Resolve a path and ensure it falls within the allowed root."""
    resolved = (allowed_root / user_path).resolve()
    if not resolved.is_relative_to(allowed_root.resolve()):
        raise ValueError(f"Path escapes allowed directory: {user_path}")
    return resolved
```

See `standards/project.md` for SD card safety rules — scripts must never write to the physical SD card without explicit user confirmation.

---

## Compliance Checklist

- [ ] No `eval()` or `exec()` with untrusted input
- [ ] No `pickle` with untrusted data
- [ ] No hardcoded secrets or credentials
- [ ] Subprocess calls use argument lists (no `shell=True`)
- [ ] Input validation uses proper libraries (Pydantic, etc.)
- [ ] Secrets loaded from environment variables
- [ ] XML parsing is safe (no entity expansion from untrusted sources)
- [ ] File path operations validated against expected directories
