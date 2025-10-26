"""System telemetry helpers shared across runtime components."""
from __future__ import annotations

import os
import platform
import shutil
import time
from pathlib import Path
from typing import Any, Callable, Optional

try:  # pragma: no cover - optional dependency
    import psutil  # type: ignore[import-untyped]
except Exception:  # pragma: no cover - psutil not bundled
    psutil = None  # type: ignore[assignment]


DocumentCounter = Optional[Callable[[], int]]


def collect_system_metrics(*, started_at: Optional[float] = None, document_counter: DocumentCounter = None) -> dict[str, Any]:
    """Collect host and runtime telemetry for dashboards and APIs.

    Parameters
    ----------
    started_at:
        Epoch timestamp corresponding to the orchestrator or daemon start
        time. Used to compute uptime in seconds.
    document_counter:
        Optional callable returning the current number of indexed documents.
        This indirection avoids importing heavy vector-store modules when the
        caller only needs host telemetry.
    """

    metrics: dict[str, Any] = {
        "hostname": platform.node(),
        "platform": platform.platform(),
        "uptime_seconds": None,
        "documents": 0,
    }

    if started_at is not None:
        metrics["uptime_seconds"] = max(0.0, time.time() - float(started_at))

    if document_counter is not None:
        try:
            metrics["documents"] = int(document_counter())
        except Exception:
            metrics["documents"] = 0

    if psutil is not None:
        try:
            metrics["cpu_percent"] = float(psutil.cpu_percent(interval=None))
        except Exception:
            metrics["cpu_percent"] = None
        try:
            vm = psutil.virtual_memory()
            metrics["memory_percent"] = float(vm.percent)
            metrics["memory_total"] = int(vm.total)
            metrics["memory_available"] = int(vm.available)
        except Exception:
            pass
        try:
            disk = psutil.disk_usage(str(Path.home()))
            metrics["disk_percent"] = float(disk.percent)
            metrics["disk_total"] = int(disk.total)
            metrics["disk_free"] = int(disk.free)
        except Exception:
            pass
        try:
            gpu_info = _collect_gpu_metrics()
            if gpu_info:
                metrics["gpu"] = gpu_info
        except Exception:
            pass
    else:
        try:
            load1, load5, load15 = os.getloadavg()
            metrics["load_average"] = {"1m": load1, "5m": load5, "15m": load15}
        except Exception:
            pass
        try:
            usage = shutil.disk_usage(str(Path.home()))
            metrics["disk_total"] = int(usage.total)
            metrics["disk_free"] = int(usage.free)
        except Exception:
            pass

    return metrics


def _collect_gpu_metrics() -> Optional[dict[str, Any]]:
    if psutil is None:  # pragma: no cover - defensive
        return None

    try:
        # Prefer pynvml if available for NVIDIA GPUs.
        import pynvml  # type: ignore[import-untyped]  # pragma: no cover - optional

        pynvml.nvmlInit()
        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            name = pynvml.nvmlDeviceGetName(handle).decode("utf-8")
            mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            return {
                "name": name,
                "memory_total": int(mem_info.total),
                "memory_used": int(mem_info.used),
                "utilization": float(util.gpu),
            }
        finally:
            pynvml.nvmlShutdown()
    except Exception:
        pass

    try:
        import subprocess

        result = subprocess.run(
            ["/usr/bin/pmset", "-g", "ps"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return {"name": "Integrated", "utilization": None, "memory_total": None, "memory_used": None}
    except Exception:
        pass

    return None


__all__ = ["collect_system_metrics"]
