# PyPI Deployment Guide for argo-kedro

## Prerequisites

1. Install build tools:
```bash
pip install build twine
```

## Build the Package

From the `argo-kedro` directory:

```bash
cd argo-kedro

# Clean previous builds
rm -rf dist/ build/ *.egg-info

# Build the package
python -m build
```

This creates:
- `dist/argo_kedro-0.1.2-py3-none-any.whl` (wheel distribution)
- `dist/argo-kedro-0.1.2.tar.gz` (source distribution)

## Test the Package Locally

```bash
# Install in a new virtual environment
python -m venv test_env
source test_env/bin/activate
pip install dist/argo_kedro-0.1.2-py3-none-any.whl

# Test the installation
python -c "import argo_kedro; print('Import successful')"

# Deactivate and remove test environment
deactivate
rm -rf test_env
```

# Install TestPyPI

```bash
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ argo-kedro
```

# Install Production Build

pip install argo-kedro

## Version Management

Update version in `pyproject.toml` before each release:

```toml
version = "0.1.0"  # Increment for each release
```

Follow semantic versioning: MAJOR.MINOR.PATCH

## Pre-release Checklist

- [ ] Update version in `pyproject.toml`
- [ ] Update README.md with latest features
- [ ] Update author information in `pyproject.toml`
- [ ] Test package builds successfully
- [ ] Test installation from built package
- [ ] All tests pass
- [ ] Update CHANGELOG (if you have one)
- [ ] Create git tag: `git tag v0.1.0 && git push origin v0.1.0`

## Post-release

After publishing:
1. Verify package appears on PyPI: https://pypi.org/project/argo-kedro/
2. Test installation: `pip install argo-kedro`
3. Check package metadata displays correctly on PyPI

## Troubleshooting

**Error: "The user 'username' isn't allowed to upload to project 'argo-kedro'"**
- First upload must use API token with "Entire account" scope
- After first upload, create project-scoped token

**Error: "File already exists"**
- You cannot replace a release on PyPI
- Increment version number and rebuild

**Error: "Invalid distribution"**
- Ensure README.md exists and is valid
- Check all required fields in pyproject.toml are filled
