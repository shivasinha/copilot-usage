/**
 * GHCP Usage Dashboard — VS Code Extension (Python Bridge)
 *
 * Architecture: spawns `python src/cli.py dashboard --port <n>` as a child
 * process, polls until ready, then opens a WebviewPanel. Manages lifecycle
 * (start/stop/deactivate) and surfaces a persistent status bar item.
 */

import * as vscode from 'vscode';
import * as cp from 'child_process';
import * as net from 'net';
import * as path from 'path';
import * as fs from 'fs';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type DashboardState = 'idle' | 'starting' | 'running' | 'error';

// ---------------------------------------------------------------------------
// Module-level state (single instance per VS Code window)
// ---------------------------------------------------------------------------

let outputChannel: vscode.OutputChannel;
let statusBarItem: vscode.StatusBarItem;
let childProcess: cp.ChildProcess | undefined;
let webviewPanel: vscode.WebviewPanel | undefined;
let currentState: DashboardState = 'idle';
let currentPort = 8080;

// ---------------------------------------------------------------------------
// Activation
// ---------------------------------------------------------------------------

export function activate(context: vscode.ExtensionContext): void {
    outputChannel = vscode.window.createOutputChannel('GHCP Usage');

    // Status bar — always visible (FR-01, US-07)
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
    statusBarItem.command = 'ghcpUsage.openDashboard';
    setStatusBarState('idle');
    statusBarItem.show();

    // Commands
    context.subscriptions.push(
        vscode.commands.registerCommand('ghcpUsage.openDashboard', () => openDashboard(context, false)),
        vscode.commands.registerCommand('ghcpUsage.stopDashboard', () => stopDashboard()),
        statusBarItem,
        outputChannel,
    );

    // Auto-open (FR-09, US-10)
    const cfg = readConfig();
    if (cfg.autoOpen) {
        setTimeout(() => openDashboard(context, true), 2000);
    }
}

export function deactivate(): void {
    // US-11: kill child process synchronously on deactivate
    killChildProcess();
}

// ---------------------------------------------------------------------------
// Config helpers
// ---------------------------------------------------------------------------

interface Config {
    pythonPath: string;
    port: number;
    autoOpen: boolean;
}

function readConfig(): Config {
    const cfg = vscode.workspace.getConfiguration('ghcpUsage');
    const rawPort = cfg.get<number | string>('port', 8080);
    let port = typeof rawPort === 'number' ? rawPort : parseInt(String(rawPort), 10);
    let portValid = Number.isInteger(port) && port >= 1024 && port <= 65535;

    if (!portValid) {
        vscode.window.showWarningMessage(
            `GHCP Usage: Invalid port value '${rawPort}'. Using default 8080.`,
            'Open Settings'
        ).then(choice => {
            if (choice === 'Open Settings') { openPortSettings(); }
        });
        port = 8080;
    }

    return {
        pythonPath: cfg.get<string>('pythonPath', '').trim(),
        port,
        autoOpen: cfg.get<boolean>('autoOpen', false),
    };
}

// ---------------------------------------------------------------------------
// Open dashboard flow (FR-02 through FR-06, US-01)
// ---------------------------------------------------------------------------

async function openDashboard(context: vscode.ExtensionContext, silent: boolean): Promise<void> {
    // Idempotent: focus existing panel if already running (US-01 scenario 3)
    if (currentState === 'running' && webviewPanel) {
        webviewPanel.reveal();
        return;
    }
    if (currentState === 'starting') {
        return; // debounce
    }

    const cfg = readConfig();
    currentPort = cfg.port;

    // --- Python check (FR-02, FR-03, US-03) ---
    const pythonExe = await resolvePython(cfg.pythonPath);
    if (!pythonExe) {
        if (!silent) {
            vscode.window.showErrorMessage(
                cfg.pythonPath
                    ? `GHCP Usage: Python executable at '${cfg.pythonPath}' not found or is not Python 3.8+.`
                    : 'GHCP Usage: Python 3.8 or higher is required but was not found. Install Python and try again.',
                'Get Python',
                'Use Custom Path'
            ).then(choice => {
                if (choice === 'Get Python') {
                    vscode.env.openExternal(vscode.Uri.parse('https://www.python.org'));
                } else if (choice === 'Use Custom Path') {
                    openPythonPathSettings();
                }
            });
        } else {
            outputChannel.appendLine('GHCP Usage: Python 3.8+ not found. Dashboard not started.');
        }
        setStatusBarState('error');
        return;
    }

    // --- Script check (US-06) ---
    const scriptPath = resolveScriptPath(context);
    if (!scriptPath) {
        if (!silent) {
            vscode.window.showErrorMessage(
                'GHCP Usage: Dashboard script not found. The extension may not be installed correctly.',
                'Open Extension Settings'
            ).then(choice => {
                if (choice === 'Open Extension Settings') { openExtensionSettings(); }
            });
        } else {
            outputChannel.appendLine('GHCP Usage: Dashboard script not found. Check extension installation.');
        }
        setStatusBarState('error');
        return;
    }

    // --- Port check (US-04) ---
    const portFree = await isPortFree(cfg.port);
    if (!portFree) {
        if (!silent) {
            vscode.window.showErrorMessage(
                `GHCP Usage: Port ${cfg.port} is already in use. Change ghcpUsage.port in settings.`,
                'Open Settings'
            ).then(choice => {
                if (choice === 'Open Settings') { openPortSettings(); }
            });
        } else {
            outputChannel.appendLine(`GHCP Usage: Port ${cfg.port} already in use.`);
        }
        setStatusBarState('error');
        return;
    }

    // --- Spawn child process (FR-04) ---
    setStatusBarState('starting');

    let progressResolve: (() => void) | undefined;
    let progressReject: ((e: Error) => void) | undefined;

    const spawnAndWait = async (): Promise<boolean> => {
        return new Promise<boolean>((resolve) => {
            outputChannel.appendLine(`[GHCP] Spawning: ${pythonExe} ${scriptPath} dashboard --port ${cfg.port}`);

            childProcess = cp.spawn(
                pythonExe,
                [scriptPath, 'dashboard', '--port', String(cfg.port)],
                {
                    shell: false, // D-05: no shell
                    cwd: path.dirname(scriptPath),
                    env: { ...process.env },
                }
            );

            childProcess.stdout?.on('data', (data: Buffer) => {
                outputChannel.appendLine('[GHCP stdout] ' + data.toString().trimEnd());
            });

            childProcess.stderr?.on('data', (data: Buffer) => {
                outputChannel.appendLine('[GHCP stderr] ' + data.toString().trimEnd());
            });

            childProcess.on('exit', (code) => {
                outputChannel.appendLine(`[GHCP] Process exited with code ${code}`);
                if (currentState !== 'idle') {
                    killChildProcess();
                    setStatusBarState('idle');
                }
            });

            childProcess.on('error', (err) => {
                outputChannel.appendLine(`[GHCP] Spawn error: ${err.message}`);
                resolve(false);
            });

            // Poll for readiness (US-05, FR-05)
            pollForReady(`http://localhost:${cfg.port}`, 10000, 500)
                .then(ready => resolve(ready));
        });
    };

    if (!silent) {
        await vscode.window.withProgress(
            { location: vscode.ProgressLocation.Notification, title: 'Starting GHCP Usage Dashboard…', cancellable: false },
            async (_progress) => {
                const ready = await spawnAndWait();
                if (!ready) {
                    killChildProcess();
                    setStatusBarState('error');
                    vscode.window.showErrorMessage(
                        'GHCP Usage: Dashboard server did not start within 10 seconds. Check the Output channel for details.',
                        'Show Output'
                    ).then(choice => {
                        if (choice === 'Show Output') { outputChannel.show(); }
                    });
                } else {
                    openPanel(context, cfg.port);
                }
            }
        );
    } else {
        const ready = await spawnAndWait();
        if (!ready) {
            killChildProcess();
            setStatusBarState('error');
            outputChannel.appendLine('GHCP Usage: Dashboard server did not start within 10 seconds.');
        } else {
            openPanel(context, cfg.port);
        }
    }
}

// ---------------------------------------------------------------------------
// WebviewPanel (FR-06, US-01)
// ---------------------------------------------------------------------------

function openPanel(context: vscode.ExtensionContext, port: number): void {
    const url = `http://localhost:${port}`;

    // Try WebviewPanel; if it fails (e.g. CSP), fall back to external browser
    try {
        webviewPanel = vscode.window.createWebviewPanel(
            'ghcpUsageDashboard',
            'GHCP Usage Dashboard',
            vscode.ViewColumn.One,
            {
                enableScripts: true,
                retainContextWhenHidden: true,
            }
        );

        webviewPanel.webview.html = buildWebviewHtml(url);

        webviewPanel.onDidDispose(() => {
            outputChannel.appendLine('[GHCP] Panel closed by user.');
            killChildProcess();
            setStatusBarState('idle');
            webviewPanel = undefined;
        }, null, context.subscriptions);

        setStatusBarState('running');
    } catch (err) {
        // Fallback to external browser (§4.1 Workflow)
        outputChannel.appendLine(`[GHCP] WebviewPanel failed, opening external browser: ${err}`);
        vscode.env.openExternal(vscode.Uri.parse(url));
        setStatusBarState('running');
    }
}

function buildWebviewHtml(url: string): string {
    // Embed the local dashboard in an iframe inside the WebviewPanel.
    // The CSP allows the localhost URL in a frame.
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="Content-Security-Policy"
    content="default-src 'none'; frame-src http://localhost:*; style-src 'unsafe-inline';">
  <style>
    html, body, iframe {
      margin: 0; padding: 0; width: 100%; height: 100%; border: none; overflow: hidden;
    }
  </style>
</head>
<body>
  <iframe src="${url}" sandbox="allow-scripts allow-same-origin allow-forms"></iframe>
</body>
</html>`;
}

// ---------------------------------------------------------------------------
// Stop dashboard (FR-07, US-02)
// ---------------------------------------------------------------------------

function stopDashboard(): void {
    killChildProcess();
    if (webviewPanel) {
        webviewPanel.dispose(); // triggers onDidDispose → idle
    } else {
        setStatusBarState('idle');
    }
}

// ---------------------------------------------------------------------------
// Process management (US-11, US-12)
// ---------------------------------------------------------------------------

let killTimer: NodeJS.Timeout | undefined;

function killChildProcess(): void {
    if (!childProcess || childProcess.exitCode !== null) {
        childProcess = undefined;
        return;
    }
    const proc = childProcess;
    childProcess = undefined;

    outputChannel.appendLine('[GHCP] Terminating child process…');

    if (process.platform === 'win32') {
        // US-12: Windows — use taskkill to also kill sub-processes
        cp.exec(`taskkill /F /T /PID ${proc.pid}`, (err) => {
            if (err) {
                outputChannel.appendLine(`[GHCP] taskkill error: ${err.message}`);
            }
        });
    } else {
        proc.kill('SIGTERM');
        // SIGKILL fallback after 2 s (US-11 scenario 3)
        killTimer = setTimeout(() => {
            if (proc.exitCode === null) {
                proc.kill('SIGKILL');
                outputChannel.appendLine('GHCP Usage: Child process did not exit gracefully; force-killed.');
            }
        }, 2000);
        proc.once('exit', () => {
            if (killTimer) { clearTimeout(killTimer); killTimer = undefined; }
        });
    }
}

// ---------------------------------------------------------------------------
// Port polling (FR-05)
// ---------------------------------------------------------------------------

function pollForReady(url: string, timeoutMs: number, intervalMs: number): Promise<boolean> {
    return new Promise((resolve) => {
        const deadline = Date.now() + timeoutMs;

        const attempt = () => {
            if (Date.now() >= deadline) {
                resolve(false);
                return;
            }
            const http = require('http') as typeof import('http');
            const req = http.get(url, (res) => {
                res.resume(); // consume response body
                if (res.statusCode && res.statusCode < 500) {
                    resolve(true);
                } else {
                    setTimeout(attempt, intervalMs);
                }
            });
            req.on('error', () => setTimeout(attempt, intervalMs));
            req.setTimeout(intervalMs, () => req.destroy());
        };

        attempt();
    });
}

// ---------------------------------------------------------------------------
// Port availability check (US-04, D-03)
// ---------------------------------------------------------------------------

function isPortFree(port: number): Promise<boolean> {
    return new Promise((resolve) => {
        const server = net.createServer();
        server.once('error', () => resolve(false));
        server.once('listening', () => { server.close(); resolve(true); });
        server.listen(port, '127.0.0.1');
    });
}

// ---------------------------------------------------------------------------
// Python resolution (FR-02, FR-03, US-03, US-12)
// ---------------------------------------------------------------------------

async function resolvePython(customPath: string): Promise<string | undefined> {
    if (customPath) {
        return await checkPythonExe(customPath) ? customPath : undefined;
    }
    // US-12: prefer python3 on Unix, python on Windows
    const candidates = process.platform === 'win32'
        ? ['python', 'python3']
        : ['python3', 'python'];
    for (const exe of candidates) {
        if (await checkPythonExe(exe)) {
            return exe;
        }
    }
    return undefined;
}

function checkPythonExe(exe: string): Promise<boolean> {
    return new Promise((resolve) => {
        // Security: exe is either a trusted config value or a fixed constant — no user input embedded in shell
        const proc = cp.spawn(exe, ['--version'], { shell: false });
        let output = '';
        proc.stdout?.on('data', (d: Buffer) => { output += d.toString(); });
        proc.stderr?.on('data', (d: Buffer) => { output += d.toString(); });
        proc.on('error', () => resolve(false));
        proc.on('close', () => {
            // Accept Python 3.8+
            const m = output.match(/Python (\d+)\.(\d+)/);
            if (!m) { resolve(false); return; }
            const major = parseInt(m[1], 10);
            const minor = parseInt(m[2], 10);
            resolve(major > 3 || (major === 3 && minor >= 8));
        });
    });
}

// ---------------------------------------------------------------------------
// Script path resolution (US-06, OQ-03)
// ---------------------------------------------------------------------------

function resolveScriptPath(context: vscode.ExtensionContext): string | undefined {
    // Try bundled resources first, then the open workspace folder (dev mode)
    const bundled = path.join(context.extensionPath, 'resources', 'src', 'cli.py');
    if (fs.existsSync(bundled)) {
        return bundled;
    }

    // Fallback: look for src/cli.py in the first workspace folder
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (workspaceFolders && workspaceFolders.length > 0) {
        const ws = path.join(workspaceFolders[0].uri.fsPath, 'src', 'cli.py');
        if (fs.existsSync(ws)) {
            return ws;
        }
    }
    return undefined;
}

// ---------------------------------------------------------------------------
// Status bar (US-07)
// ---------------------------------------------------------------------------

function setStatusBarState(state: DashboardState): void {
    currentState = state;
    switch (state) {
        case 'idle':
            statusBarItem.text = '$(graph) GHCP';
            statusBarItem.tooltip = 'Open GHCP Usage Dashboard';
            statusBarItem.command = 'ghcpUsage.openDashboard';
            statusBarItem.color = undefined;
            break;
        case 'starting':
            statusBarItem.text = '$(sync~spin) GHCP';
            statusBarItem.tooltip = 'GHCP Dashboard starting…';
            statusBarItem.command = undefined;
            break;
        case 'running':
            statusBarItem.text = '$(circle-filled) GHCP';
            statusBarItem.tooltip = 'GHCP Dashboard running — click to focus';
            statusBarItem.command = 'ghcpUsage.openDashboard';
            break;
        case 'error':
            statusBarItem.text = '$(error) GHCP';
            statusBarItem.tooltip = 'GHCP Dashboard error — click to retry';
            statusBarItem.command = 'ghcpUsage.openDashboard';
            break;
    }
}

// ---------------------------------------------------------------------------
// Settings helpers
// ---------------------------------------------------------------------------

function openPortSettings(): void {
    vscode.commands.executeCommand('workbench.action.openSettings', 'ghcpUsage.port');
}

function openPythonPathSettings(): void {
    vscode.commands.executeCommand('workbench.action.openSettings', 'ghcpUsage.pythonPath');
}

function openExtensionSettings(): void {
    vscode.commands.executeCommand('workbench.action.openSettings', 'ghcpUsage');
}
