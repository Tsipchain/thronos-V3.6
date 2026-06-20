# Hotfix: BNB Watcher SyntaxError (Deployment #dbbee3)

## Problem

Deployment `dbbee370` (commit `7b9367fe`) fails at runtime with:

```
File "/app/server.py", line 27019
    global _BNB_WATCHER_AVAILABLE
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
SyntaxError: annotated name '_BNB_WATCHER_AVAILABLE' can't be global
```

In Python 3.11, a variable that has a type annotation at module scope (e.g.,
`_BNB_WATCHER_AVAILABLE: bool = False`) cannot be declared `global` inside a
function. PR #681 introduced this conflict.

## Fix Required

In `server.py`, find the module-level declaration:

```python
_BNB_WATCHER_AVAILABLE: bool = False
```

Replace it with (remove the type annotation):

```python
_BNB_WATCHER_AVAILABLE = False
```

This allows the `global _BNB_WATCHER_AVAILABLE` statement at line 27019 to
work correctly under Python 3.11. The type annotation provides no runtime
behavior, so removing it is safe.

## Status

The `server.py` file on the current HEAD appears to be empty (0 bytes).
The file must be restored from the previous working commit (`de5db072`)
and the above fix applied before redeployment.
