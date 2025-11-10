# PyPubSub Testing

## Setup and Running Tests

### Initial Setup

To run tests, you need to install the project with test dependencies:

```bash
# Install all dependencies including test extras
uv sync --all-extras
```

**Why `--all-extras`?**
- `uv sync` only installs the main dependencies
- `uv sync --all-extras` installs optional dependencies defined in `[project.optional-dependencies]`
- Tests require extra packages like `pytest`, `easydict`, and `asfpy` that are not needed for production

### Running Tests

Once dependencies are synced with `--all-extras`, you can run tests:

```bash
# Run matrix.py test
uv run python tests/matrix.py

# Or run from the tests directory
cd tests
uv run python matrix.py
```

### Workflow Summary

1. **First time setup or after dependency changes:**
   ```bash
   uv sync --all-extras
   ```

2. **Running the server (production):**
   ```bash
   # Only needs main dependencies, so plain "uv run" works
   uv run pypubsub.py --config pypubsub.yaml --acl pypubsub_acl.yaml
   ```

3. **Running tests (development):**
   ```bash
   # Requires test extras to be installed first
   uv sync --all-extras
   uv run python tests/matrix.py
   ```

### Common Issues

**Problem:** `ModuleNotFoundError: No module named 'easydict'` or `'asfpy'`

**Solution:** Run `uv sync --all-extras` to install test dependencies

---

**Problem:** `ModuleNotFoundError: No module named 'pypubsub'`

**Solution:** The test uses `sys.path` manipulation to import
pypubsub. Make sure you're running from the project root or tests
directory, and that `pyproject.toml` is properly configured with
`py-modules = ["pypubsub"]` and `packages = ["plugins"]`
