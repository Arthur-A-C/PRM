"""Hard memory limits for the isolated decoder/model process; fail closed if unavailable."""
import os

_job_handle = None


def limit_memory(mib):
    global _job_handle
    size = mib * 1024 * 1024
    if os.name != 'nt':
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (size, size))
        return
    import ctypes
    from ctypes import wintypes
    class Basic(ctypes.Structure):
        _fields_ = [('ProcessTime', ctypes.c_longlong), ('JobTime', ctypes.c_longlong),
                    ('Flags', wintypes.DWORD), ('MinWorking', ctypes.c_size_t), ('MaxWorking', ctypes.c_size_t),
                    ('Processes', wintypes.DWORD), ('Affinity', ctypes.c_size_t), ('Priority', wintypes.DWORD), ('Scheduling', wintypes.DWORD)]
    class Counters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in ['ReadOps','WriteOps','OtherOps','ReadBytes','WriteBytes','OtherBytes']]
    class Limits(ctypes.Structure):
        _fields_ = [('Basic', Basic), ('IO', Counters), ('ProcessMemory', ctypes.c_size_t),
                    ('JobMemory', ctypes.c_size_t), ('PeakProcess', ctypes.c_size_t), ('PeakJob', ctypes.c_size_t)]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    handle = kernel.CreateJobObjectW(None, None)
    limits = Limits(); limits.Basic.Flags = 0x100; limits.ProcessMemory = size
    if not handle or not kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)) or not kernel.AssignProcessToJobObject(handle, kernel.GetCurrentProcess()):
        raise RuntimeError('Não foi possível limitar memória do processo ASR')
    _job_handle = handle  # Keep job alive for this interpreter's lifetime.
