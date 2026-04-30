# Security Policy

This package may process sensitive legal, regulatory, or client PDFs.

## Supported Versions

The current supported integration release is `v0.1.0`.

## Reporting Issues

Open a private report with the maintainers if possible. If private reporting is unavailable, open a GitHub issue without attaching sensitive PDFs or full document text.

Include:

- package version
- operating system
- provider configuration
- environment validation output
- minimal reproduction steps

Do not include:

- full source documents
- full page OCR output
- secrets, tokens, or private endpoints

## Data Handling Expectations

- Local providers are the default.
- Remote services must be explicitly configured by the caller/operator.
- Logs should not contain full page content.
- Error snippets should remain bounded.
