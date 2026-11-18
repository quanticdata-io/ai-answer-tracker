# Security policy

## Reporting a vulnerability

Please do not open a public issue for security problems. Email **hello@quanticdata.io** with the subject "Security: ai-answer-tracker" and include a description, steps to reproduce and the version you use. We acknowledge reports within 3 business days and keep you informed until a fix is released.

## Supported versions

| Version | Supported |
| --- | --- |
| 0.1.x | yes |

## API keys and stored data

Never commit an API key. The tool reads `QUANTICDATA_API_KEY` from the environment and sends it only in the `Authorization` header to the API base URL (`QUANTICDATA_API_BASE`, default `https://api.quanticdata.io/v1`). In CI, store the key as an encrypted secret. If a key leaks, rotate it on the API keys page of the QuanticData dashboard.

The SQLite history file holds your questions and answer excerpts. Keep it out of public repositories if the questions are confidential (`*.db` is in `.gitignore`).
