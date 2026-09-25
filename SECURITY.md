# Security policy

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub's
[security advisories](https://github.com/DweskZ/EcuDataMCP/security/advisories/new),
not in public issues. Include the affected version, the tool or endpoint
involved, and steps to reproduce.

Maintainers aim to acknowledge reports within 7 days.

## Supported versions

Only the latest release on `main` receives security fixes.

## Scope

In scope: the MCP server itself (HTTP transport, Bearer auth, rate limiting,
download and decompression limits, file parsing). Out of scope: the upstream
government portals the server reads from.
