"""OS-level resource limits, applied by the sandbox process to itself.

Imported by `_sandbox_runner.py` inside the child process, before any generated
code runs. Layer 3 of the sandbox (see SECURITY.md).

POSIX  -- `resource.setrlimit`: heap size, output file size, subprocess
          count, and core dumps.
Windows -- a Job Object via ctypes: process memory cap, an active-process limit
          of 1 (so `CreateProcess` fails), and kill-on-close so nothing survives
          the parent. Windows has no `resource` module, and without this the
          memory cap would silently not exist on the primary dev platform.

Every function is best-effort: a limit that cannot be applied is reported in the
return value rather than raised, because failing to sandbox is not a reason to
fail the user's question -- but it must be visible.
"""
from __future__ import annotations

import os
import sys

# Held for the lifetime of the process: closing the Job Object handle while we
# are still inside the job would trigger KILL_ON_JOB_CLOSE and kill us.
_JOB_HANDLE = None


# The runner is always launched as `python -I .../_sandbox_runner.py ...`, so
# argv[0] identifies it. The guard is not paranoia: these limits are applied to
# the *calling* process and are irreversible. Calling this from the API process
# would put it in a job with ActiveProcessLimit=1, and every later attempt to
# start a sandbox would die with "Not enough quota is available".
_RUNNER_NAME = "_sandbox_runner.py"


def apply_limits(memory_mb: int, output_mb: int) -> list[str]:
    """Apply what this platform supports. Returns the labels actually applied.

    Only callable from inside the sandbox subprocess -- see the note above.
    """
    caller = os.path.basename(sys.argv[0] or "")
    if caller != _RUNNER_NAME:
        raise RuntimeError(
            f"apply_limits() may only be called by {_RUNNER_NAME}, not by "
            f"{caller or 'an unknown process'}: the limits are irreversible and "
            "would cripple the calling process."
        )

    if sys.platform == "win32":
        return _apply_windows(memory_mb)
    return _apply_posix(memory_mb, output_mb)


def _apply_posix(memory_mb: int, output_mb: int) -> list[str]:
    try:
        import resource
    except ImportError:  # pragma: no cover - POSIX only
        return []

    applied: list[str] = []
    # RLIMIT_DATA, not RLIMIT_AS. RLIMIT_AS bounds *virtual* address space, and
    # a CPython process with pandas and numpy imported reserves far more of that
    # than it ever touches -- shared-library mappings, numpy's arena. Since the
    # limit is applied after those imports (see _sandbox_runner.main), an AS cap
    # sized to real memory use succeeds at setrlimit() and then fails the very
    # next allocation, so every question dies with a spurious MemoryError.
    # RLIMIT_DATA bounds the heap, where pandas allocations actually land, so it
    # can be sized against expected peak RSS. On Linux >= 4.7 it covers brk plus
    # private anonymous mmap; on macOS it only covers brk, so the cap is weaker
    # there and the wall-clock timeout is the effective backstop.
    limits = [
        ("memory", getattr(resource, "RLIMIT_DATA", None), memory_mb * 1024 * 1024),
        ("output-size", getattr(resource, "RLIMIT_FSIZE", None), output_mb * 1024 * 1024),
        ("subprocesses", getattr(resource, "RLIMIT_NPROC", None), 0),
        ("core-dumps", getattr(resource, "RLIMIT_CORE", None), 0),
    ]
    for label, which, value in limits:
        if which is None:
            continue
        try:
            soft, hard = resource.getrlimit(which)
            capped = value if hard == resource.RLIM_INFINITY else min(value, hard)
            resource.setrlimit(which, (capped, hard))
            applied.append(label)
        except (ValueError, OSError):
            continue
    return applied


# --- Windows Job Object -----------------------------------------------------

_JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9


def _apply_windows(memory_mb: int) -> list[str]:  # pragma: no cover - win32 only
    global _JOB_HANDLE
    import ctypes
    from ctypes import wintypes

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
            ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),  # ULONG_PTR
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    # argtypes are not optional here: GetCurrentProcess returns the pseudo-handle
    # -1, which ctypes cannot marshal into an inferred C int.
    kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        return []

    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = (
        _JOB_OBJECT_LIMIT_PROCESS_MEMORY
        | _JOB_OBJECT_LIMIT_ACTIVE_PROCESS
        | _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    )
    info.BasicLimitInformation.ActiveProcessLimit = 1
    info.ProcessMemoryLimit = memory_mb * 1024 * 1024

    ok = kernel32.SetInformationJobObject(
        job, _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
        ctypes.byref(info), ctypes.sizeof(info),
    )
    if not ok:
        kernel32.CloseHandle(job)
        return []

    if not kernel32.AssignProcessToJobObject(job, kernel32.GetCurrentProcess()):
        kernel32.CloseHandle(job)
        return []

    _JOB_HANDLE = job  # must outlive this function; see module docstring
    return ["memory", "subprocesses", "kill-on-close"]
