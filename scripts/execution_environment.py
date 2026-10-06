# FEATURE: Portfolio_Foundry_v0.38.0.20.16309_BUILD49_TEST62
"""Read-only machine inventory and optional process-scoped GPU observations.

No packages, drivers or runtimes are installed. Unknown data stays null.
DXGI SIZE_T memory is used on Windows, never Win32_VideoController.AdapterRAM.
"""
import argparse
import csv
import ctypes
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time
import uuid


FEATURE_TOKEN = "Portfolio_Foundry_v0.38.0.20.16309_BUILD49_TEST62"
FEATURE_REVISION = "PATCH_READY1"
PATCH_TOKEN = os.environ.get("PORTFOLIO_FOUNDRY_PATCH_TOKEN", "PATCH_V031_RUNTIME_DESCRIPTOR_DEPS19")


def with_provenance(value):
    return dict(value, featureToken=FEATURE_TOKEN, featureRevision=FEATURE_REVISION, patchToken=PATCH_TOKEN)


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def key(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def atomic(path, value):
    value = with_provenance(value)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def number(value):
    try:
        result = int(str(value).strip())
        return result if result >= 0 else None
    except (ValueError, TypeError):
        return None


def command(args, timeout=3):
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    try:
        p = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout, **options)
        return p.stdout.strip() if p.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def read(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def nvidia_tool():
    found = shutil.which("nvidia-smi")
    if found:
        return found
    if os.name == "nt":
        for root in (os.environ.get("SystemRoot", "C:\\Windows"), os.environ.get("ProgramFiles", "C:\\Program Files")):
            for relative in ("System32/nvidia-smi.exe", "NVIDIA Corporation/NVSMI/nvidia-smi.exe"):
                p = Path(root) / relative
                if p.is_file():
                    return str(p)
    return None


def parse_nvidia_inventory(text):
    result = []
    for row in csv.reader((text or "").splitlines()):
        if len(row) != 4:
            continue
        identity, name, memory, driver = [x.strip() for x in row]
        if not identity.startswith("GPU-"):
            continue
        memory = number(memory)
        result.append(dict(id="gpu-" + key(identity), model=name, vendor="NVIDIA",
                           dedicatedVramBytes=memory * 1048576 if memory is not None else None,
                           sharedSystemMemoryBytes=None, driverVersion=driver if driver != "N/A" else None,
                           memorySource="nvidia-smi", computeObservation="nvidia-smi process sampling"))
    return result


class Luid(ctypes.Structure):
    _fields_ = [("low", ctypes.c_uint32), ("high", ctypes.c_int32)]


class AdapterDesc(ctypes.Structure):
    _fields_ = [("description", ctypes.c_uint16 * 128), ("vendor", ctypes.c_uint32),
                ("device", ctypes.c_uint32), ("subsystem", ctypes.c_uint32), ("revision", ctypes.c_uint32),
                ("dedicated", ctypes.c_size_t), ("system", ctypes.c_size_t),
                ("shared", ctypes.c_size_t), ("luid", Luid)]


def dxgi_adapters():
    if os.name != "nt":
        return []
    def method(obj, index, result, *args):
        table = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        return ctypes.WINFUNCTYPE(result, ctypes.c_void_p, *args)(table[index])
    factory = ctypes.c_void_p()
    create = ctypes.WinDLL("dxgi").CreateDXGIFactory
    create.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    create.restype = ctypes.c_int32
    iid = (ctypes.c_ubyte * 16).from_buffer_copy(uuid.UUID("7b7166ec-21c7-44ae-b21a-c9ae321ae369").bytes_le)
    if create(ctypes.byref(iid), ctypes.byref(factory)) < 0:
        return []
    result = []
    try:
        for index in range(32):
            adapter = ctypes.c_void_p()
            hr = method(factory, 7, ctypes.c_int32, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p))(factory, index, ctypes.byref(adapter))
            if hr < 0:
                break
            try:
                desc = AdapterDesc()
                if method(adapter, 8, ctypes.c_int32, ctypes.POINTER(AdapterDesc))(adapter, ctypes.byref(desc)) < 0:
                    continue
                name = bytes(desc.description).decode("utf-16-le").split("\0", 1)[0]
                # Software adapters are not physical video cards.
                if desc.vendor == 0x1414 or "software" in name.lower():
                    continue
                result.append(dict(id="dxgi-" + key(f"{desc.luid.high}:{desc.luid.low}"), model=name,
                    vendor={0x10DE:"NVIDIA", 0x1002:"AMD", 0x8086:"Intel"}.get(desc.vendor, hex(desc.vendor)),
                    dedicatedVramBytes=int(desc.dedicated) if ctypes.sizeof(ctypes.c_size_t)==8 else None,
                    sharedSystemMemoryBytes=int(desc.shared) if ctypes.sizeof(ctypes.c_size_t)==8 else None,
                    driverVersion=None, memorySource="DXGI SIZE_T", computeObservation="unavailable"))
            finally:
                method(adapter, 2, ctypes.c_uint32)(adapter)
    finally:
        method(factory, 2, ctypes.c_uint32)(factory)
    return result


WINDOWS_QUERY = r"""
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$o=Get-CimInstance Win32_OperatingSystem
$m=Get-CimInstance Win32_ComputerSystem
$c=@(Get-CimInstance Win32_Processor)
$v=@(Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion)
$d=@(); try { $d=@(Get-CimInstance -Namespace root/Microsoft/Windows/Storage -ClassName MSFT_PhysicalDisk | Select-Object DeviceId,FriendlyName,MediaType,Size) } catch {}
@{machine=@{manufacturer=$m.Manufacturer;model=$m.Model};os=@{name=$o.Caption;version=$o.Version;build=$o.BuildNumber;architecture=$o.OSArchitecture};
cpu=@{models=@($c|ForEach-Object {$_.Name});physicalCores=($c|Measure-Object NumberOfCores -Sum).Sum;logicalCores=($c|Measure-Object NumberOfLogicalProcessors -Sum).Sum};
ramBytes=([long]$o.TotalVisibleMemorySize*1024);video=$v;disks=$d} | ConvertTo-Json -Depth 6 -Compress
"""


def collect_hardware():
    unavailable = []
    hardware = dict(machine=dict(manufacturer=None,model=None),os=dict(name=platform.system(), release=platform.release(), version=platform.version(),
                           architecture=platform.machine()),
                    cpu=dict(models=[platform.processor()] if platform.processor() else [], physicalCores=None,
                             logicalCores=os.cpu_count()), ram=dict(totalBytes=None), disks=[], gpus=[], computeTools=[])
    if os.name == "nt":
        output = command(["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", WINDOWS_QUERY], 7)
        try:
            win = json.loads(output or "{}")
        except ValueError:
            win = {}
        if win:
            hardware["machine"].update(win.get("machine") or {})
            hardware["os"].update(win.get("os") or {})
            hardware["cpu"].update(win.get("cpu") or {})
            hardware["ram"]["totalBytes"] = number(win.get("ramBytes"))
            for d in win.get("disks") or []:
                hardware["disks"].append(dict(id=str(d.get("DeviceId")), model=d.get("FriendlyName"),
                    mediaType={3:"HDD",4:"SSD",5:"SCM"}.get(number(d.get("MediaType")), "UNKNOWN"),
                    sizeBytes=number(d.get("Size")), source="Windows Storage CIM"))
        else:
            unavailable.append("Windows CIM inventory unavailable or timed out")
        try:
            hardware["gpus"] = dxgi_adapters()
        except (OSError, ValueError, AttributeError):
            unavailable.append("DXGI inventory unavailable")
        videos = win.get("video") or []
        for gpu in hardware["gpus"]:
            matches = [v for v in videos if v.get("Name") == gpu["model"]]
            if matches:
                gpu["driverVersion"] = matches[0].get("DriverVersion")
        if not hardware["gpus"]:
            for i, v in enumerate(videos):
                hardware["gpus"].append(dict(id="display-"+str(i),model=v.get("Name"),vendor=None,
                    dedicatedVramBytes=None,sharedSystemMemoryBytes=None,driverVersion=v.get("DriverVersion"),
                    memorySource="unavailable",computeObservation="unavailable"))
    elif sys.platform.startswith("linux"):
        if not Path('/proc/meminfo').is_file():
            unavailable.append('Linux procfs unavailable; CPU/RAM details are unknown')
        hardware["machine"]=dict(manufacturer=read('/sys/class/dmi/id/sys_vendor') or None,model=read('/sys/class/dmi/id/product_name') or None)
        cpu = read("/proc/cpuinfo")
        models = sorted(set(re.findall(r"^model name\s*:\s*(.+)$", cpu, re.M)))
        if models:
            hardware["cpu"]["models"] = models
        cores = set()
        for block in cpu.split("\n\n"):
            physical = re.search(r"^physical id\s*:\s*(\d+)", block, re.M)
            core = re.search(r"^core id\s*:\s*(\d+)", block, re.M)
            if physical and core:
                cores.add((physical[1], core[1]))
        hardware["cpu"]["physicalCores"] = len(cores) or None
        memory = re.search(r"^MemTotal:\s*(\d+)", read("/proc/meminfo"), re.M)
        hardware["ram"]["totalBytes"] = int(memory[1])*1024 if memory else None
        for disk in Path("/sys/block").glob("*"):
            if disk.name.startswith(("loop", "ram", "zram")):
                continue
            sectors = number(read(disk / "size"))
            rotational = read(disk / "queue/rotational")
            hardware["disks"].append(dict(id=disk.name, model=read(disk / "device/model") or disk.name,
                mediaType={"0":"NON_ROTATING", "1":"HDD"}.get(rotational, "UNKNOWN"),
                sizeBytes=sectors*512 if sectors is not None else None, source="Linux sysfs"))
        for device in Path("/sys/class/drm").glob("card[0-9]*"):
            if "-" in device.name:
                continue
            vendor = read(device / "device/vendor")
            if not vendor:
                continue
            memory = number(read(device / "device/mem_info_vram_total"))
            hardware["gpus"].append(dict(id="drm-"+device.name,model=device.name+" · "+read(device / "device/device"),
                vendor={"0x10de":"NVIDIA","0x1002":"AMD","0x8086":"Intel"}.get(vendor,vendor),
                dedicatedVramBytes=memory,sharedSystemMemoryBytes=None,driverVersion=None,
                memorySource="Linux DRM" if memory is not None else "unavailable",computeObservation="unavailable"))
    else:
        unavailable.append("Detailed hardware inventory is supported on Windows and Linux")
    smi = nvidia_tool()
    if smi:
        gpus = parse_nvidia_inventory(command([smi, "--query-gpu=uuid,name,memory.total,driver_version", "--format=csv,noheader,nounits"]))
        if gpus:
            for gpu in gpus:
                matches = [g for g in hardware["gpus"] if g["model"] == gpu["model"]]
                if len(matches) == 1 and sum(g["model"] == gpu["model"] for g in gpus) == 1:
                    gpu["sharedSystemMemoryBytes"] = matches[0]["sharedSystemMemoryBytes"]
            hardware["gpus"] = [g for g in hardware["gpus"] if g["vendor"] != "NVIDIA"] + gpus
            hardware["computeTools"].append(dict(name="NVIDIA driver",version=gpus[0]["driverVersion"],meaning="driver, not CUDA Toolkit"))
    for executable, args, name in (("nvcc",["--version"],"CUDA Toolkit"),("hipconfig",["--version"],"HIP / ROCm")):
        path = shutil.which(executable)
        if path:
            text = command([path]+args, 2)
            if text:
                version = re.search(r"release\s+([\d.]+)",text)
                hardware["computeTools"].append(dict(name=name,version=version[1] if version else text[-180:],meaning="installed tool"))
    if not hardware["gpus"]:
        unavailable.append("No GPU reported by available inventory sources; this does not prove physical absence")
    return hardware, unavailable


def save_snapshot(history_root, hardware, build, unavailable=(), duration_ms=0):
    root = Path(history_root)
    root.mkdir(parents=True, exist_ok=True)
    identity_file = root / "machine-id.txt"
    # Exclusive create makes simultaneous probes use the same local identity.
    try:
        with identity_file.open("x", encoding="ascii") as stream:
            stream.write(uuid.uuid4().hex)
    except FileExistsError:
        pass
    machine = "machine-" + key(read(identity_file))[:12]
    local = datetime.datetime.now().astimezone()
    stable = dict(featureToken=FEATURE_TOKEN, featureRevision=FEATURE_REVISION, machineId=machine, hardware=hardware, build=build,
                  timezone=dict(name=str(local.tzinfo), offsetMinutes=int(local.utcoffset().total_seconds()/60)))
    snapshot_id = key(json.dumps(stable, sort_keys=True))
    snapshot = dict(schema="foundry.execution-environment.v1", snapshotId=snapshot_id, **stable,
                    capturedAt=stamp(), probe=dict(durationMs=duration_ms,unavailable=list(unavailable)))
    path = root / "environments" / (snapshot_id+".json")
    if not path.exists():
        atomic(path, snapshot)
    return json.loads(path.read_text(encoding="utf-8"))


def process_tree(root_pid):
    parents = {}
    if os.name == "nt":
        class Entry(ctypes.Structure):
            _fields_=[("size",ctypes.c_uint32),("usage",ctypes.c_uint32),("pid",ctypes.c_uint32),
                ("heap",ctypes.c_size_t),("module",ctypes.c_uint32),("threads",ctypes.c_uint32),
                ("parent",ctypes.c_uint32),("priority",ctypes.c_int32),("flags",ctypes.c_uint32),
                ("exe",ctypes.c_wchar*260)]
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateToolhelp32Snapshot.restype=ctypes.c_void_p
        kernel.Process32FirstW.argtypes=[ctypes.c_void_p,ctypes.POINTER(Entry)]
        kernel.Process32NextW.argtypes=[ctypes.c_void_p,ctypes.POINTER(Entry)]
        kernel.CloseHandle.argtypes=[ctypes.c_void_p]
        handle=kernel.CreateToolhelp32Snapshot(2,0)
        if handle == ctypes.c_void_p(-1).value:
            raise OSError('Windows process inventory unavailable')
        try:
            entry=Entry();entry.size=ctypes.sizeof(entry)
            ok=kernel.Process32FirstW(handle,ctypes.byref(entry))
            while ok:
                parents[int(entry.pid)]=int(entry.parent)
                ok=kernel.Process32NextW(handle,ctypes.byref(entry))
        finally:
            kernel.CloseHandle(handle)
    else:
        if not Path('/proc').is_dir():
            raise OSError('Process inventory unavailable: procfs is not mounted')
        for p in Path('/proc').glob('[0-9]*/stat'):
            text=read(p)
            if text:
                fields=text.rsplit(')',1)[-1].split()
                if len(fields)>1:
                    parents[int(p.parent.name)]=int(fields[1])
    if root_pid not in parents:
        return set()
    found={root_pid}
    while True:
        children={pid for pid,parent in parents.items() if parent in found}
        more=children-found
        if not more:
            return found
        found.update(more)


def parse_compute_sample(text, pids):
    totals = {}
    for row in csv.reader((text or "").splitlines()):
        if len(row) != 3:
            continue
        pid, identity, memory = [x.strip() for x in row]
        if number(pid) not in pids or not identity.startswith("GPU-"):
            continue
        gpu_id="gpu-"+key(identity); used=number(memory)
        if gpu_id not in totals:
            totals[gpu_id]=0
        totals[gpu_id]=None if used is None or totals[gpu_id] is None else totals[gpu_id]+used*1048576
    return totals


def observe(request):
    started=time.monotonic()
    target=Path(request["recordPath"]); stop=Path(request["stopPath"])
    result=with_provenance(request["record"])
    result.update(samples=0, gpuStatus="NOT_SAMPLED", gpus=[], source="nvidia-smi compute-process samples",
                  peakKind="maximum observed sample; not a guaranteed absolute peak", sampleIntervalSeconds=2)
    smi=nvidia_tool(); peaks={}; errors=0
    try:
        while not stop.exists() and smi and time.monotonic()-started < 7200:
            pids=process_tree(int(request["pid"]))
            if not pids:
                break
            text=command([smi,"--query-compute-apps=pid,gpu_uuid,used_memory","--format=csv,noheader,nounits"],2)
            if text is None:
                errors+=1
            else:
                result["samples"]+=1
                for gpu_id, memory in parse_compute_sample(text,pids).items():
                    previous=peaks.get(gpu_id)
                    peaks[gpu_id]=max(previous or 0,memory) if memory is not None else previous
            result["gpuStatus"]="OBSERVED" if peaks else ("NOT_OBSERVED" if result["samples"] else "UNAVAILABLE")
            result["gpus"]=[dict(id=k,peakObservedVramBytes=v) for k,v in peaks.items()]
            atomic(target,result)
            if errors>=3:
                break
            for _ in range(10):
                if stop.exists(): break
                time.sleep(.2)
    except (OSError, ValueError, AttributeError):
        result['gpuStatus']='OBSERVED' if peaks else 'UNAVAILABLE'
        errors+=1
    finally:
        if not smi:
            result["gpuStatus"]="UNAVAILABLE"
        result.update(endedAt=stamp(), observationErrors=errors)
        atomic(target,result)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--snapshot', action='store_true')
    parser.add_argument('--history-root')
    parser.add_argument('--build-version', default='unknown')
    parser.add_argument('--build-token', default='unknown')
    parser.add_argument('--observe')
    args=parser.parse_args()
    if args.observe:
        observe(json.loads(Path(args.observe).read_text(encoding='utf-8-sig')))
        return
    before=time.monotonic()
    hardware, missing=collect_hardware()
    hardware['cacheVolume']=Path(args.history_root).anchor
    hardware['probePython']=dict(version=platform.python_version(),implementation=platform.python_implementation(),architecture=platform.machine())
    result=save_snapshot(args.history_root,hardware,dict(version=args.build_version,token=args.build_token),missing,(time.monotonic()-before)*1000)
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    main()
