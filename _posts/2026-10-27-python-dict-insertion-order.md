---
title: Python dicts preserve insertion order (since 3.7)
tags: [python]
---

Since Python 3.7, the built-in `dict` is guaranteed to preserve insertion order.
(CPython 3.6 already did it as an implementation detail; 3.7 made it part of
the language spec.)

```python
d = {}
d["b"] = 1
d["a"] = 2
d["c"] = 3

list(d)        # ['b', 'a', 'c']
```

A few details worth knowing:

- Updating an existing key keeps its original position; deleting and
  re-inserting moves it to the end.
- Iteration over `keys()`, `values()` and `items()` all follow the same order.
- `collections.OrderedDict` is still useful when you need `move_to_end()` or
  order-sensitive equality (`OrderedDict` comparisons care about order, plain
  `dict` comparisons don't).
