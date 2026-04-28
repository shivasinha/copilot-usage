# Changelog

All notable changes to the **Copilot Usage Dashboard** VS Code extension are documented here.
This file follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) conventions
and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.5] — 2026-04-28
### Changed
- Renamed Command Palette commands to `GHCP Usage: Open Dashboard` and `GHCP Usage: Stop Dashboard`.
- Updated repository, homepage, and bugs URLs to `github.com/shivasinha/ghcp-usage`.
- Added `claude` keyword to extension manifest.

## [0.2.4] — 2026-04-28
### Changed
- Default premium request quota limit raised from 100 to 300.

## [0.2.3] — 2026-04-28
### Added
- Reload Window notification on fresh install or version upgrade.
- Python resolution now queries the VS Code Python extension's active interpreter first.
- Windows fallback probes common Python install locations (LOCALAPPDATA, ProgramFiles, C:\Python3xx) when python is not on PATH.
- Added `py` launcher as a candidate on Windows.

## [0.2.2] — 2026-04-28
### Removed
- Proxy data source option fully removed from the Data Source dropdown and backend filtering logic.

## [0.2.1] — 2026-04-28
### Fixed
- Added missing models to the pricing table.
- Extension icon updated to the official GitHub Copilot icon.

### Changed
- Renamed Command Palette commands:
  - `GHCP: Open Usage Dashboard` → `Copilot Usage: Open Dashboard`
  - `GHCP: Stop Dashboard` → `Copilot Usage: Stop Dashboard`

## [0.2.0] — 2026-04-01
### Added
- Status bar item with live state indicator (idle / starting / running / error).
- `ghcpUsage.autoOpen` setting — automatically opens the dashboard when VS Code starts.
- Port conflict detection with an actionable error message and link to settings.
- Python version validation (requires Python 3.8+).
- Output channel (`GHCP Usage`) for diagnostic logging.

## [0.1.0] — 2026-03-01
### Added
- Initial release.
- Spawns the Python dashboard server and opens it in a VS Code WebView panel.
- Configurable Python executable path (`ghcpUsage.pythonPath`).
- Configurable HTTP port (`ghcpUsage.port`, default `8080`).
