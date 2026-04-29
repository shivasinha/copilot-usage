# Changelog

All notable changes to **Copilot Usage Dashboard** are documented here.

## [0.2.7] — 2026-04-29
### Fixed
- Scanner now discovers session files with the `.json` extension used by VS Code ≥ 1.100, in addition to the legacy `.jsonl` extension. This was the root cause of dashboards showing 0 data on machines running recent VS Code versions.

## [0.2.1] — 2026-04-28
### Fixed
- Added missing models to the pricing table.

## [0.2.0] — 2026-04-01
### Added
- Status bar item with live state indicator.
- `autoOpen` setting to start the dashboard on VS Code startup.
- Port conflict detection with actionable error message.
- Python version validation (requires 3.8+).
- Output channel for diagnostic logging.

### Changed
- Renamed commands to `GHCP Usage: Open Dashboard` and `GHCP Usage: Stop Dashboard`.

## [0.1.0] — 2026-03-01
### Added
- Initial release.
- Spawns Python dashboard server and opens it in a VS Code WebView panel.
- Configurable Python path and port.
