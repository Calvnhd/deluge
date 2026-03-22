# Technical Specification: [Feature Name]

> **Document Type:** Technical Specification  
> **Phase:** [X of Y if part of a larger plan, or "Standalone"]  
> **Status:** Draft | In Review | Approved | Implemented  
> **Date:** [YYYY-MM-DD]  
> **Parent Plan:** [Link to plan if applicable, or "N/A"]

---

## Overview

Technical summary of the feature being implemented. Explain:
- What this feature does
- Why it matters (the problem it solves)
- How it fits into the larger system

---

## Requirements

### Functional Requirements

- **FR1:** Description of functional requirement.
- **FR2:** Description of functional requirement.

### Non-Functional Requirements

- **NFR1:** Performance, maintainability, or other quality requirements.
- **NFR2:** Coding conventions, documentation standards, etc.

---

## Architecture

### Component Overview

Description of components involved and their relationships. Include:
- Where this component lives in the project structure
- Dependencies on other components
- Components that will depend on this one

### Class Diagram / Structure

```
[ASCII diagram showing class relationships, inheritance, composition, etc.]
```

### Relationship to Other Components

| Component | Relationship |
|-----------|--------------|
| [Name]    | [How they interact] |

---

## Detailed Design

### New Classes / Types

| Class Name | Purpose | Location |
|------------|---------|----------|
|            |         |          |

### Modified Classes

| Class Name | Changes Required |
|------------|------------------|
|            |                  |

### Key Methods

#### `MethodName(parameters)`

- **Purpose:** What the method does.
- **Parameters:** 
  - `paramName`: Description and constraints.
- **Returns:** Return value description with edge cases.
- **Notes:** Implementation considerations, algorithm notes.

---

## Implementation

Explain the algorithm or design decisions in plain language. Use:
- Visual diagrams (ASCII art) to illustrate concepts
- Step-by-step breakdowns of complex logic
- Examples showing input → output

This section helps junior engineers understand *why* the code works, not just *what* it does.

---

## Integration Points

How this feature integrates with existing systems. Show:
- Example usage code from consuming components
- Which future phases/features depend on this

```csharp
// Example: How Phase N will use this component
```

---

## Testing Strategy

### Test Cases

| Test Case | Setup | Expected Result |
|-----------|-------|-----------------|
|           |       |                 |

### Manual Validation

Describe how to manually verify the feature works:
- Steps to run validation code
- What to observe
- How to clean up test code afterward

---

## Acceptance Criteria

- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Solution compiles without errors or warnings
- [ ] All test cases pass

---

## Implementation Notes

### Code Comments vs Spec Documentation

> **Important:** This spec is the learning resource. Code comments should be **concise summaries only** — do not copy tuning guides, examples, or step-by-step explanations into XML documentation. Developers can refer to this spec for detailed explanations.

### For the Implementer

Step-by-step guidance:
1. File creation instructions
2. Namespace and using statements
3. Build verification commands
4. Validation steps

### Design Decisions Explained

| Decision | Rationale |
|----------|-----------|
| [Choice made] | [Why this approach was chosen] |

### Common Pitfalls to Avoid

1. **Pitfall Name:** Description of what to watch out for and why it's problematic.

---

## References

- [Link to relevant documentation]
- [Link to sample code or patterns]
- [Link to related project files]
