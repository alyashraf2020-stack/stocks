"""Single-instance locks and parent-owned Windows process trees."""

from contextlib import contextmanager
import os
import subprocess

WINDOWS = os.name == "nt"


@contextmanager
def lock(path):
    with path.open("a+b") as stream:
        if stream.tell() == 0:
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        if WINDOWS:
            import msvcrt

            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise BlockingIOError("Another EGX process holds the lock") from exc
        else:
            import fcntl

            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
        # Closing the handle releases the lock, including after a crash.


class Children:
    def __init__(self):
        self.children = []
        self.job = None
        self.child_jobs = {}
        if WINDOWS:
            self.kernel, self.job = create_job()

    def spawn(self, args, **options):
        if WINDOWS:
            options["creationflags"] = options.get("creationflags", 0) | 0x00000004
        child = subprocess.Popen(args, **options)
        if WINDOWS:
            child_job = None
            try:
                handle = int(child._handle)
                if not self.kernel.AssignProcessToJobObject(self.job, handle):
                    raise OSError(
                        "Windows could not assign EGX process to the supervision job"
                    )
                _, child_job = create_job()
                if not self.kernel.AssignProcessToJobObject(child_job, handle):
                    raise OSError("Windows could not isolate the EGX service tree")
                resume_child(self.kernel, child.pid)
            except OSError:
                if child_job:
                    self.kernel.CloseHandle(child_job)
                child.kill()
                child.wait()
                raise
            self.child_jobs[child] = child_job
        self.children = [process for process in self.children if process.poll() is None]
        self.children.append(child)
        return child

    def exited(self, child):
        job = self.child_jobs.pop(child, None)
        if job:
            self.kernel.CloseHandle(job)

    def close(self):
        for child in list(self.child_jobs):
            self.exited(child)
        if self.job:
            self.kernel.CloseHandle(self.job)
            self.job = None
        else:
            for process in self.children:
                if process.poll() is None:
                    process.terminate()
        for process in self.children:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def create_job():
    import ctypes
    from ctypes import wintypes as wt

    class BasicLimits(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wt.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wt.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wt.DWORD),
            ("SchedulingClass", wt.DWORD),
        ]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimits),
            ("IoInfo", ctypes.c_ulonglong * 6),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wt.LPCWSTR]
    kernel.CreateJobObjectW.restype = wt.HANDLE
    kernel.SetInformationJobObject.argtypes = [
        wt.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wt.DWORD,
    ]
    kernel.AssignProcessToJobObject.argtypes = [wt.HANDLE, wt.HANDLE]
    kernel.CloseHandle.argtypes = [wt.HANDLE]
    job = kernel.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    limits = ExtendedLimits()
    limits.BasicLimitInformation.LimitFlags = (
        0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    )
    if not kernel.SetInformationJobObject(
        job, 9, ctypes.byref(limits), ctypes.sizeof(limits)
    ):
        error = ctypes.get_last_error()
        kernel.CloseHandle(job)
        raise ctypes.WinError(error)
    return kernel, job


def resume_child(kernel, pid):
    # Popen closes the initial thread handle. A suspended child has not had a
    # chance to start descendants before both Job Objects are in place.
    import ctypes
    from ctypes import wintypes as wt

    class ThreadEntry(ctypes.Structure):
        _fields_ = [
            ("size", wt.DWORD),
            ("usage", wt.DWORD),
            ("thread", wt.DWORD),
            ("process", wt.DWORD),
            ("priority", wt.LONG),
            ("delta", wt.LONG),
            ("flags", wt.DWORD),
        ]

    kernel.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wt.HANDLE
    kernel.Thread32First.argtypes = [wt.HANDLE, ctypes.POINTER(ThreadEntry)]
    kernel.Thread32Next.argtypes = kernel.Thread32First.argtypes
    kernel.OpenThread.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
    kernel.OpenThread.restype = wt.HANDLE
    kernel.ResumeThread.argtypes = [wt.HANDLE]
    kernel.ResumeThread.restype = wt.DWORD
    snapshot = kernel.CreateToolhelp32Snapshot(0x4, 0)  # TH32CS_SNAPTHREAD
    if snapshot == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        row = ThreadEntry(size=ctypes.sizeof(ThreadEntry))
        found = kernel.Thread32First(snapshot, ctypes.byref(row))
        while found and row.process != pid:
            row.size = ctypes.sizeof(ThreadEntry)
            found = kernel.Thread32Next(snapshot, ctypes.byref(row))
        if not found:
            raise OSError("No initial Windows service thread was found")
        thread = kernel.OpenThread(0x2, False, row.thread)  # THREAD_SUSPEND_RESUME
        if not thread:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if kernel.ResumeThread(thread) == 0xFFFFFFFF:
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            kernel.CloseHandle(thread)
    finally:
        kernel.CloseHandle(snapshot)
