# services/ops/scheduler.py
from __future__ import annotations

import os
import threading
import time
from typing import Any, Dict, Optional, Tuple

from services.ops.healer import run_heal_scan_once

_stop_flag = False
_thread: Optional[threading.Thread] = None

# status
_running = False
_last_run_ts: Optional[int] = None         # 上一次“扫描完成”的时间（秒）
_next_run_ts: Optional[int] = None         # 预计下一次运行时间（秒）
_last_summary: Optional[Dict[str, Any]] = None
_last_error: Optional[str] = None

# debug/observe
_pid: int = os.getpid()
_thread_ident: Optional[int] = None


def _get_runtime_value(key: str) -> Tuple[Any, str]:
    """
    生效优先级：DB override（前端） > settings/.env > default
    returns: (value, source) where source in {"db","env","default"}
    """
    try:
        from services.ops.runtime_config import get_value  # type: ignore
        return get_value(key)
    except Exception:
        try:
            from config import settings  # type: ignore
            return getattr(settings, key, None), "env"
        except Exception:
            return None, "default"


def _cfg_int(key: str, default: int, *, min_v: Optional[int] = None, max_v: Optional[int] = None) -> int:
    v, _ = _get_runtime_value(key)
    try:
        n = int(str(v).strip())
    except Exception:
        n = default
    if min_v is not None and n < min_v:
        n = min_v
    if max_v is not None and n > max_v:
        n = max_v
    return n


def _cfg_bool(key: str, default: bool) -> bool:
    v, _ = _get_runtime_value(key)
    if v is None:
        return default
    s = str(v).strip().lower()
    if s in ("1", "true", "yes", "y", "on"):
        return True
    if s in ("0", "false", "no", "n", "off"):
        return False
    return default


def _cfg_str(key: str, default: str = "") -> str:
    v, _ = _get_runtime_value(key)
    s = str(v or "").strip()
    return s if s else default


def _get_interval_sec() -> int:
    """
    每轮动态读取 interval（DB override > env > default）
    安全下限：避免误配成 0/1 秒把集群打爆
    """
    v = _cfg_int("HEAL_INTERVAL_SEC", 60, min_v=5, max_v=3600)
    return v


def _sleep_interruptible(total_sec: int) -> None:
    """
    可中断 sleep：stop_healer() 后最多 1 秒内停止。
    另外：如果运行时把 HEAL_ENABLED 关掉，也会尽快退出。
    """
    end = time.time() + max(0, int(total_sec))
    while not _stop_flag and time.time() < end:
        if not _cfg_bool("HEAL_ENABLED", True):
            break
        time.sleep(1)


def start_healer(namespace: Optional[str] = None) -> None:
    """
    启动自愈定时器（后台线程）。
    - namespace=None => 全集群扫描（会被 healer 里的 allow/deny 再过滤）
    注意：如果你用 uvicorn --reload 或多进程 workers，线程在哪个进程跑取决于启动方式。
    """
    global _thread, _stop_flag, _running, _pid, _thread_ident
    global _last_run_ts, _next_run_ts, _last_summary, _last_error

    # ✅ 没启用就不启动
    if not _cfg_bool("HEAL_ENABLED", True):
        return

    # 如果已经有活着的线程，就不重复启动
    if _thread and _thread.is_alive():
        return

    # 如果有线程对象但已死，清理一下
    _thread = None
    _thread_ident = None

    _stop_flag = False
    _running = True
    _pid = os.getpid()
    _last_error = None

    def loop():
        global _running, _last_run_ts, _next_run_ts, _last_summary, _last_error, _thread_ident

        _thread_ident = threading.get_ident()

        while not _stop_flag:
            # ✅ 运行中被关掉：立即退出循环
            if not _cfg_bool("HEAL_ENABLED", True):
                break

            interval = _get_interval_sec()
            now = int(time.time())
            _next_run_ts = now + interval  # 先预估下一次

            try:
                res = run_heal_scan_once(namespace=namespace)

                # ✅ “扫描完成”再写 last_run，更符合语义
                _last_run_ts = int(time.time())

                _last_summary = {
                    "ok": res.get("ok"),
                    "checked": res.get("checked"),
                    "attempted": res.get("attempted"),
                    "healed": res.get("healed"),
                    "dry_run": res.get("dry_run"),
                    "skipped": res.get("skipped"),
                }
                _last_error = None
            except Exception as e:
                _last_error = str(e)

            # ✅ 可中断 sleep，stop 后不会卡满 interval
            _sleep_interruptible(interval)

        _running = False

    _thread = threading.Thread(target=loop, name="kube-guard-healer", daemon=True)
    _thread.start()


def stop_healer(timeout_sec: int = 3) -> None:
    """
    停止后台线程：设 stop flag + join。
    """
    global _stop_flag, _thread, _running

    _stop_flag = True

    t = _thread
    if t and t.is_alive():
        try:
            t.join(timeout=timeout_sec)
        except Exception:
            pass

    _running = False


def get_status() -> Dict[str, Any]:
    """
    给前端 /api/ops/heal/status 用：
    你一眼能看出：是否在当前进程跑、线程 ident、最近扫描完成时间、下一次预计运行。
    """
    interval = _get_interval_sec()
    alive = bool(_thread and _thread.is_alive())

    enabled = _cfg_bool("HEAL_ENABLED", True)
    execute = _cfg_bool("HEAL_EXECUTE", False)
    max_per_cycle = _cfg_int("HEAL_MAX_PER_CYCLE", 3, min_v=1, max_v=50)
    cooldown_sec = _cfg_int("HEAL_COOLDOWN_SEC", 300, min_v=0, max_v=3600)

    # allow_ns 你 settings 里可能没有，这里默认空字符串
    allow_ns = _cfg_str("HEAL_ALLOW_NS", "")
    deny_ns = _cfg_str("HEAL_DENY_NS", "")
    only_reasons = _cfg_str("HEAL_ONLY_REASONS", "")

    return {
        "running": bool(_running and alive),
        "pid": _pid,
        "thread_ident": _thread_ident,
        "interval_sec": interval,
        "last_run_ts": _last_run_ts,
        "next_run_ts": _next_run_ts,
        "last_summary": _last_summary,
        "last_error": _last_error,
        "enabled": enabled,
        "execute": execute,
        "max_per_cycle": max_per_cycle,
        "cooldown_sec": cooldown_sec,
        "allow_ns": allow_ns,
        "deny_ns": deny_ns,
        "only_reasons": only_reasons,
    }
