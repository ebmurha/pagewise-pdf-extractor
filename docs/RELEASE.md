# Release Process

This project is intended to be consumed by other repositories as a normal Python dependency. Consumers must pin to an immutable version, tag, or commit.

## Best Practice

Use semantic versioning and immutable Git tags:

- Patch release: bug fixes that do not change the public API, for example `0.1.1`
- Minor release: backward-compatible features, for example `0.2.0`
- Major release: breaking public API changes, for example `1.0.0`

Before the API is stable, use `0.x.y` versions. For `rag-engine`, prefer a release tag such as `v0.1.0` over a raw commit SHA once the first integration build is accepted.

## Pre-Release Checklist

1. Confirm `pyproject.toml` version.
2. Confirm `pagewise_pdf_extractor.__version__` reports the same version.
3. Run tests:

   ```powershell
   python -m unittest discover -s tests -p "test_*.py"
   ```

4. Run install and CLI smoke checks:

   ```powershell
   python -m pip install -e .
   python -c "from pagewise_pdf_extractor import ExtractionConfig, process_pdf, validate_environment; print('ok')"
   pagewise-pdf-extractor --help
   pagewise-pdf-extractor --validate-environment
   ```

5. Verify docs:

   - `README.md`
   - `PDF_TOOL_PROJECT_OVERVIEW.md`
   - `docs/PACKAGING.md`
   - `docs/RELEASE.md`

6. Commit the release-ready state.

## Create a Tag

Use an annotated tag:

```powershell
git tag -a v0.1.0 -m "Release v0.1.0"
git push origin v0.1.0
```

Annotated tags are preferred for public collaborator workflows because they carry release metadata and are clearer than lightweight tags.

## Dependency Pinning

For `rag-engine`, pin to the tag:

```txt
pagewise-pdf-extractor @ git+https://github.com/ebmurha/pagewise-pdf-extractor.git@v0.1.0
```

During pre-release validation, pinning to a commit SHA is acceptable:

```txt
pagewise-pdf-extractor @ git+https://github.com/ebmurha/pagewise-pdf-extractor.git@<commit-sha>
```

Do not pin a consumer to `main`. Branches move, which makes builds non-reproducible.

## PyPI Publication

PyPI publication is optional until the public API stabilizes. When publishing later:

1. Build artifacts from a clean checkout.
2. Upload to TestPyPI first if needed.
3. Upload to PyPI.
4. Create a matching GitHub release for the same tag.

Consumers can then use:

```txt
pagewise-pdf-extractor>=0.1.0
```

Consumer repositories should still choose an explicit upper bound or lockfile according to their dependency policy.
