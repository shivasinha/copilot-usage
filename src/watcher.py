"""File-system watcher for VS Code Copilot JSONL log directories.

Fires a callback whenever a .jsonl file changes, so the dashboard can
trigger an immediate re-scan instead of waiting for the polling interval.

Platform strategy (all stdlib, no pip):
  Windows  — ReadDirectoryChangesW via ctypes
  Linux    — inotify via ctypes
  macOS    — stat-based polling (kqueue requires select module extras)

Usage:
    from watcher import start_watching

    def on_change():
        scanner.scan(log_dir)

    stop = start_watching(log_dir, on_change, debounce_seconds=2.0)
    # ...
    stop()  # call to stop the watcher thread

The watcher runs in a daemon thread — it is automatically cleaned up when
the process exits.  `on_change` is called from that thread; keep it short
or dispatch to another thread if needed.
"""

import os
import sys
import threading
import time
from pathlib import Path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start_watching(directory, callback, debounce_seconds=2.0):
    """Start watching *directory* for .jsonl changes.

    Returns a callable that stops the watcher when called.

    Parameters
    ----------
    directory : str | Path
        The directory to watch (recursively on Windows/Linux; top-level only
        on the polling fallback).
    callback : callable
        Called (with no arguments) when one or more .jsonl files change.
        Calls are debounced so rapid successive writes trigger only one call.
    debounce_seconds : float
        How long to wait after the last detected change before firing.
    """
    directory = Path(directory)
    stop_event = threading.Event()

    if sys.platform == "win32":
        target = _watch_windows
    elif sys.platform == "linux":
        target = _watch_linux
    else:
        target = _watch_poll

    t = threading.Thread(
        target=target,
        args=(directory, callback, debounce_seconds, stop_event),
        daemon=True,
        name="ghcp-watcher",
    )
    t.start()

    return stop_event.set


# ---------------------------------------------------------------------------
# Debounce helper
# ---------------------------------------------------------------------------

class _Debouncer:
    """Fires callback at most once per `delay` seconds after the last trigger."""

    def __init__(self, callback, delay):
        self._callback = callback
        self._delay = delay
        self._lock = threading.Lock()
        self._timer = None

    def trigger(self):
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self._delay, self._fire)
            self._timer.daemon = True
            self._timer.start()

    def _fire(self):
        with self._lock:
            self._timer = None
        try:
            self._callback()
        except Exception:
            pass  # never crash the watcher thread


# ---------------------------------------------------------------------------
# Windows: ReadDirectoryChangesW
# ---------------------------------------------------------------------------

def _watch_windows(directory, callback, debounce_seconds, stop_event):
    """Watch using Win32 ReadDirectoryChangesW (overlapped, non-blocking poll)."""
    import ctypes
    import ctypes.wintypes as wt

    FILE_LIST_DIRECTORY    = 0x0001
    FILE_SHARE_ALL         = 0x07
    OPEN_EXISTING          = 3
    FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
    FILE_FLAG_OVERLAPPED   = 0x40000000
    FILE_NOTIFY_CHANGE_LAST_WRITE = 0x10
    FILE_NOTIFY_CHANGE_FILE_NAME  = 0x01
    WAIT_OBJECT_0 = 0x00000000
    WAIT_TIMEOUT  = 0x00000102
    INVALID_HANDLE_VALUE  = ctypes.c_void_p(-1).value

    k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

    handle = k32.CreateFileW(
        str(directory),
        FILE_LIST_DIRECTORY,
        FILE_SHARE_ALL,
        None,
        OPEN_EXISTING,
        FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OVERLAPPED,
        None,
    )
    if handle == INVALID_HANDLE_VALUE or handle == 0:
        # Fall back to polling if we can't open the directory
        _watch_poll(directory, callback, debounce_seconds, stop_event)
        return

    event_handle = k32.CreateEventW(None, True, False, None)
    if not event_handle:
        k32.CloseHandle(handle)
        _watch_poll(directory, callback, debounce_seconds, stop_event)
        return

    BUF_SIZE = 65536
    buf = ctypes.create_string_buffer(BUF_SIZE)
    overlapped = ctypes.create_string_buffer(32)  # OVERLAPPED struct
    ctypes.memset(overlapped, 0, 32)
    # Set hEvent in OVERLAPPED (offset 24 on 64-bit, but we use the event separately)

    debouncer = _Debouncer(callback, debounce_seconds)

    def _issue():
        bytes_returned = ctypes.c_ulong(0)
        k32.ReadDirectoryChangesW(
            handle,
            buf,
            BUF_SIZE,
            True,  # watch subtree
            FILE_NOTIFY_CHANGE_LAST_WRITE | FILE_NOTIFY_CHANGE_FILE_NAME,
            ctypes.byref(bytes_returned),
            overlapped,
            None,
        )

    # Use GetOverlappedResult with a manual event via a simpler synchronous call
    # Fall back to the simpler synchronous (blocking) variant with a timeout thread
    k32.CloseHandle(event_handle)
    k32.CloseHandle(handle)

    # Use the simpler synchronous ReadDirectoryChangesW in a loop with stop_event
    handle = k32.CreateFileW(
        str(directory),
        FILE_LIST_DIRECTORY,
        FILE_SHARE_ALL,
        None,
        OPEN_EXISTING,
        FILE_FLAG_BACKUP_SEMANTICS,
        None,
    )
    if handle == INVALID_HANDLE_VALUE or handle == 0:
        _watch_poll(directory, callback, debounce_seconds, stop_event)
        return

    # Run blocking ReadDirectoryChangesW in a sub-thread so we can stop it
    change_event = threading.Event()

    def _blocking_loop():
        bytes_returned = ctypes.c_ulong(0)
        local_buf = ctypes.create_string_buffer(BUF_SIZE)
        while not stop_event.is_set():
            ok = k32.ReadDirectoryChangesW(
                handle,
                local_buf,
                BUF_SIZE,
                True,
                FILE_NOTIFY_CHANGE_LAST_WRITE | FILE_NOTIFY_CHANGE_FILE_NAME,
                ctypes.byref(bytes_returned),
                None,
                None,
            )
            if not ok:
                break
            # Check if any changed file is a .jsonl
            try:
                data = bytes(local_buf[:bytes_returned.value])
                if b".jsonl" in data or b"jsonl" in data.lower():
                    debouncer.trigger()
                else:
                    # Any write to the directory — could be a new file
                    debouncer.trigger()
            except Exception:
                debouncer.trigger()

    bt = threading.Thread(target=_blocking_loop, daemon=True, name="ghcp-watcher-win32")
    bt.start()

    stop_event.wait()
    k32.CloseHandle(handle)  # unblocks ReadDirectoryChangesW


# ---------------------------------------------------------------------------
# Linux: inotify
# ---------------------------------------------------------------------------

def _watch_linux(directory, callback, debounce_seconds, stop_event):
    """Watch using Linux inotify syscall via ctypes."""
    import ctypes
    import ctypes.util
    import select
    import struct

    try:
        libc_name = ctypes.util.find_library("c") or "libc.so.6"
        libc = ctypes.CDLL(libc_name, use_errno=True)
    except Exception:
        _watch_poll(directory, callback, debounce_seconds, stop_event)
        return

    IN_CLOSE_WRITE = 0x00000008
    IN_MOVED_TO    = 0x00000080
    IN_CREATE      = 0x00000100

    inotify_init = libc.inotify_init
    inotify_init.restype = ctypes.c_int
    inotify_add_watch = libc.inotify_add_watch
    inotify_add_watch.restype = ctypes.c_int

    fd = inotify_init()
    if fd < 0:
        _watch_poll(directory, callback, debounce_seconds, stop_event)
        return

    # Watch the top-level directory (JSONL files are 2 levels deep but we
    # walk subdirs to add watches for each chatSessions dir)
    watches = {}
    mask = IN_CLOSE_WRITE | IN_MOVED_TO | IN_CREATE

    def _add_watches(root):
        for dirpath, dirnames, _ in os.walk(str(root)):
            wd = inotify_add_watch(fd, dirpath.encode(), mask)
            if wd >= 0:
                watches[wd] = dirpath

    _add_watches(directory)

    debouncer = _Debouncer(callback, debounce_seconds)
    EVENT_HEADER = struct.Struct("iIII")  # wd, mask, cookie, name_len

    try:
        while not stop_event.is_set():
            r, _, _ = select.select([fd], [], [], 1.0)
            if not r:
                continue
            raw = os.read(fd, 4096)
            offset = 0
            while offset < len(raw):
                if offset + EVENT_HEADER.size > len(raw):
                    break
                wd, ev_mask, cookie, name_len = EVENT_HEADER.unpack_from(raw, offset)
                offset += EVENT_HEADER.size
                name = raw[offset:offset + name_len].rstrip(b"\x00").decode(errors="replace")
                offset += name_len
                if name.endswith(".jsonl"):
                    debouncer.trigger()
    finally:
        os.close(fd)


# ---------------------------------------------------------------------------
# Fallback: polling
# ---------------------------------------------------------------------------

def _watch_poll(directory, callback, debounce_seconds, stop_event):
    """Polling fallback: stat every .jsonl file every 3 seconds."""
    directory = Path(directory)
    debouncer = _Debouncer(callback, debounce_seconds)
    known = {}  # path -> mtime

    while not stop_event.is_set():
        try:
            current = {}
            for f in directory.rglob("*.jsonl"):
                try:
                    current[f] = f.stat().st_mtime
                except OSError:
                    pass
            changed = any(current.get(p) != known.get(p) for p in current) or \
                      any(p not in current for p in known)
            if changed:
                debouncer.trigger()
            known = current
        except Exception:
            pass
        stop_event.wait(3.0)
