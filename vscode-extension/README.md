# GHCP Usage Dashboard

**Author:** Shiva Sinha

Track your GitHub Copilot usage — token counts, model breakdown, session history, and estimated cost — directly inside VS Code.

## Requirements

- Python 3.8 or later must be installed on your machine.  
  [Download Python](https://www.python.org/downloads/)

## Getting Started

1. Install the extension.
2. Click the **📊 GHCP** item in the status bar, or open the Command Palette (`Ctrl+Shift+P`) and run **Copilot Usage: Open Dashboard**.
3. The dashboard opens in a panel and shows your Copilot usage history.

## Commands

| Command | Description |
|---|---|
| **Copilot Usage: Open Dashboard** | Opens (or focuses) the usage dashboard. |
| **Copilot Usage: Stop Dashboard** | Stops the background dashboard server. |

## Settings

| Setting | Default | Description |
|---|---|---|
| `ghcpUsage.pythonPath` | *(system PATH)* | Path to a specific Python 3.8+ executable. Leave empty to use the Python on your system PATH. |
| `ghcpUsage.port` | `8080` | Local port for the dashboard server. Change this if port 8080 is already in use. |
| `ghcpUsage.autoOpen` | `false` | Automatically open the dashboard when VS Code starts. |


