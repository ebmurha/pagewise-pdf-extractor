# Releases and Versioning

This package is versioned so applications can depend on a specific, reproducible build.

## Current Release

The current documented release is `v0.2.0`.

`0.2.0` is an early integration release. The package is usable by downstream applications, but the public API may still change before `1.0.0`.

## Version Numbers

Versions follow semantic versioning:

- Patch versions, such as `0.1.1`, contain fixes that should not change the public API.
- Minor versions, such as `0.2.0`, may add backward-compatible features.
- Major versions, such as `1.0.0`, may include breaking API changes.

Before `1.0.0`, minor versions may still include API adjustments. Pin exact versions or use a lockfile for production workloads.

## Installing a Release

From PyPI when available:

```powershell
python -m pip install pagewise-pdf-extractor==0.2.0
```

From GitHub:

```txt
pagewise-pdf-extractor @ git+https://github.com/ebmurha/pagewise-pdf-extractor.git@v0.2.0
```

Avoid depending on `main`. Branches move, which makes installs non-reproducible.

## Compatibility Expectations

The supported public API is exported from `pagewise_pdf_extractor`:

```python
from pagewise_pdf_extractor import ExtractionConfig, process_pdf, validate_environment
```

Imports from internal modules, provider implementations, or repository scripts are not part of the compatibility contract.

## Release Notes

- [v0.2.0](releases/v0.2.0.md)
- [v0.1.1](releases/v0.1.1.md)
- [v0.1.0](releases/v0.1.0.md)

Check the changelog for package-level changes across releases:

- [Changelog](../CHANGELOG.md)
