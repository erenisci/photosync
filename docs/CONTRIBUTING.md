# Contributing to PhotoSync

Thanks for your interest in PhotoSync! This guide covers the development setup
and the conventions we follow.

## Development setup

Requires Python 3.11+.

```bash
git clone <repo-url>
cd photosync
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Unix:     source .venv/bin/activate
pip install -e ".[dev]"
```

To run the application against rclone you also need the bundled binaries:

```bash
python scripts/download_rclone.py
```

## Quality gates

All three must pass before a change is merged (CI enforces them):

```bash
ruff check .        # lint + import order
mypy                # static type checking (strict)
pytest              # tests
```

`ruff format .` applies the canonical formatting.

## Conventions

- **Type hints everywhere.** The codebase runs mypy in `strict` mode; every
  function has annotated parameters and return types. New modules should start
  with `from __future__ import annotations`.
- **No secrets on disk in our code.** Credentials and OAuth tokens are owned by
  rclone and encrypted with the user's master password. `settings.json` holds
  only non-secret configuration.
- **All rclone calls go through `app/rclone_client.py`**, always with
  `shell=False` and an argument list (never string interpolation) to avoid
  injection. Pass the master password via the `RCLONE_CONFIG_PASS` environment
  variable and clear it afterward.
- **Filesystem locations come from `app/paths.py`.** Don't hardcode paths; the
  app must stay portable across "frozen" (PyInstaller) and development modes.
- **Tests use `tmp_path`** and monkeypatch `paths.*` rather than touching real
  drive locations. Keep tests hermetic and fast.

## Scope

The MVP is complete. Future work should be sliced into focused PRs (one
feature/fix per PR). See [ARCHITECTURE.md](ARCHITECTURE.md) for the module map.

When extending catalog mode, remember the safety invariant: **upload first,
then replace the original**. Anything that touches `app/stub.py` or the
catalog branch of `app/sync_engine.py` must preserve "no data loss on upload
failure" as a hard property and ship with a test that verifies it.

## Adding a cloud provider

rclone supports [70+ providers](https://rclone.org/overview/); PhotoSync ships
with four of them in the wizard. Adding another one is intentionally cheap.

### OAuth providers (Box, pCloud, Mega, Yandex, …)

If the provider uses `rclone authorize <type>`:

1. Create `app/providers/<name>.py`:

   ```python
   from __future__ import annotations

   from app.providers.base import OAuthProvider


   class Box(OAuthProvider):
       def __init__(self) -> None:
           super().__init__(name="Box", rclone_type="box")
   ```

2. Register it in `app/providers/__init__.py`:

   ```python
   from app.providers.box import Box

   ALL_PROVIDERS: list[CloudProvider] = [
       GoogleDrive(),
       Dropbox(),
       OneDrive(),
       Box(),            # ← add here
       S3Compatible(),
   ]
   ```

3. Add `Box` to the `__all__` list.

That's it — the wizard picks it up automatically, the OAuth flow goes through
`rclone authorize box`, and the rest of the pipeline is shared.

### Non-OAuth / custom providers

If the provider takes credentials directly (like S3) rather than an OAuth flow,
subclass `CloudProvider` instead of `OAuthProvider` and implement
`setup_params()` and `get_target_path_label()`. Look at
[`app/providers/s3_compatible.py`](../app/providers/s3_compatible.py) as a
worked example — it handles a credentials form and presets for popular S3
services. The wizard already has a generic credentials screen pattern that
can be reused.

### Tests

Add at least one entry to `tests/test_providers.py` checking that
`setup_params()` returns the expected rclone config keys for your provider.

## Project conventions for issues

When the repository is published, issue templates will exist for bug reports,
feature requests, and security disclosures. Security-sensitive reports should use
the private security disclosure channel rather than a public issue.

## Commit messages

Write clear, imperative commit subjects ("Add scan cache invalidation", not
"added stuff"). Reference the phase or module where helpful.
