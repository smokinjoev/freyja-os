# Certification Report: freyja-iterative-coding

## Summary

- Timestamp: 2026-08-25T17:30:51+00:00
- Git SHA: 1735657802883d32f32dbb0e6db7b08b1238d19b
- Branch: main
- Working tree: dirty
- Hostname: iris.lan
- Provider: local_reasoning
- Model: gpt-oss-freyja:20b-analysis-prefill
- Router mode: default
- Suite: freyja-iterative-coding
- Overall score: 1.000
- Passing score: 0.900
- Passed: True
- Execution time: 37.452s
- Mean generation speed: 30.372 tokens/s
- Speed samples: 10
- Certification CLI version: 0.1.0

## Category Scores

- Coding: 100.0%

- Overall: 100.0%

## Failed Cases

No failed cases.

## Cases

### coding/freyja-iterative-coding: python-fix-off-by-one

- Difficulty: standard
- Passed: True
- Score: 1.000 / 1.000

Prompt:

```
You are revising code after a failed unit test.

Broken code:
```python
def inclusive_range_total(start, end):
    return sum(range(start, end))
```

Failed expectation: inclusive_range_total(1, 3) should return 6.

Return only the corrected Python function.

```

Response:

```
```python
def inclusive_range_total(start, end):
    return sum(range(start, end + 1))
```

```

### coding/freyja-iterative-coding: python-preserve-empty-list

- Difficulty: standard
- Passed: True
- Score: 1.000 / 1.000

Prompt:

```
First attempt failed because empty input raised an exception.

Broken code:
```python
def average(values):
    return sum(values) / len(values)
```

Requirement: return 0 for an empty list, otherwise return the arithmetic mean.

Return only the corrected Python function.

```

Response:

```
```python
def average(values):
    if not values:
        return 0
    return sum(values) / len(values)
```

```

### coding/freyja-iterative-coding: javascript-fix-sort-numeric

- Difficulty: standard
- Passed: True
- Score: 1.000 / 1.000

Prompt:

```
A JavaScript test failed:
sortNumbers([10, 2, 1]) returned [1, 10, 2], expected [1, 2, 10].

Broken code:
```javascript
function sortNumbers(values) {
  return values.sort();
}
```

Return only the corrected function.

```

Response:

```
```javascript
function sortNumbers(values) {
  return values.sort((a, b) => a - b);
}
```

```

### coding/freyja-iterative-coding: python-fix-mutable-default

- Difficulty: standard
- Passed: True
- Score: 1.000 / 1.000

Prompt:

```
A second call leaked state from the first call.

Broken code:
```python
def add_tag(tag, tags=[]):
    tags.append(tag)
    return tags
```

Requirement: each omitted tags argument should start fresh.

Return only the corrected Python function.

```

Response:

```
```python
def add_tag(tag, tags=None):
    if tags is None:
        tags = []
    tags.append(tag)
    return tags
```

```

### coding/freyja-iterative-coding: python-fix-case-insensitive-count

- Difficulty: standard
- Passed: True
- Score: 1.000 / 1.000

Prompt:

```
Tests show count_word("Hello hello", "hello") should return 2, but the current version returns 1.

Broken code:
```python
def count_word(text, word):
    return text.split().count(word)
```

Return only the corrected Python function.

```

Response:

```
```python
def count_word(text, word):
    """Count occurrences of *word* in *text*, case‑insensitively."""
    target = word.lower()
    return sum(1 for token in text.split() if token.lower() == target)
```

```

### coding/freyja-iterative-coding: python-fix-json-error-handling

- Difficulty: standard
- Passed: True
- Score: 1.000 / 1.000

Prompt:

```
The first implementation crashes on malformed JSON.

Broken code:
```python
import json

def read_name(raw):
    return json.loads(raw)["name"]
```

Requirement: return None when the JSON is invalid or when "name" is missing.

Return only the corrected Python code.

```

Response:

```
```python
import json

def read_name(raw):
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    return data.get("name")
```

```

### coding/freyja-iterative-coding: typescript-fix-null-guard

- Difficulty: standard
- Passed: True
- Score: 1.000 / 1.000

Prompt:

```
Review this TypeScript function after a crash when user is null.

Broken code:
```typescript
function displayName(user: { first: string; last: string } | null): string {
  return user.first + " " + user.last;
}
```

Requirement: return "Unknown" when user is null.

Return only the corrected function.

```

Response:

```
```typescript
function displayName(user: { first: string; last: string } | null): string {
  return user ? `${user.first} ${user.last}` : "Unknown";
}
```

```

### coding/freyja-iterative-coding: python-fix-deduplicate-stable

- Difficulty: standard
- Passed: True
- Score: 1.000 / 1.000

Prompt:

```
The current implementation removes duplicates but changes order.

Requirement: unique_stable(["b", "a", "b"]) returns ["b", "a"].

Return only a Python function named unique_stable.

```

Response:

```
```python
def unique_stable(seq):
    """Return a list of the elements in *seq* with duplicates removed,
    preserving the original order of first occurrences."""
    seen = set()
    result = []
    for item in seq:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
```
```

### coding/freyja-iterative-coding: python-fix-context-manager-close

- Difficulty: standard
- Passed: True
- Score: 1.000 / 1.000

Prompt:

```
A resource leak test failed because the file was not closed on exceptions.

Broken code:
```python
def read_first_line(path):
    f = open(path)
    return f.readline()
```

Return only the corrected Python function.

```

Response:

```
```python
def read_first_line(path):
    with open(path, "r") as f:
        return f.readline()
```

```

### coding/freyja-iterative-coding: python-fix-boundary-validation

- Difficulty: standard
- Passed: True
- Score: 1.000 / 1.000

Prompt:

```
A validation test failed: clamp(11, 0, 10) should return 10 and clamp(-1, 0, 10) should return 0.

Return only a Python function named clamp(value, minimum, maximum).

```

Response:

```
```python
def clamp(value, minimum, maximum):
    """Clamp `value` to the inclusive range [minimum, maximum]."""
    if value < minimum:
        return minimum
    if value > maximum:
        return maximum
    return value
```

```
