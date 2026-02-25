# services/inspect/checks.py
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from kubernetes.client.rest import ApiException

from services.inspect.models import InspectItem
from services.k8s.kube_client import get_core_v1, get_apps_v1

# Prometheus 可选
try:
    from services.monitoring.prometheus_client import instant_value  # type: ignore
except Exception:
    instant_value = None  # type: ignore


def _ms(t0: float) -> int:
    return int((time.time() - t0) * 1000)


def _rbac_detail(need: str) -> str:
    return f"权限不足/需要 RBAC: {need}"


def _api_exc_to_item(
    *,
    key: str,
    title: str,
    need_rbac: str,
    e: ApiException,
    t0: float,
) -> InspectItem:
    # 403 => warn（可以继续巡检其他项）
    if getattr(e, "status", None) == 403:
        return InspectItem(
            key=key,
            title=title,
            level="warn",
            detail=f"{_rbac_detail(need_rbac)}；K8s API 返回 403",
            suggestion="给运行巡检的 ServiceAccount/用户增加对应 list/get 权限，或改用 kubeconfig 模式运行。",
            evidence={"status": getattr(e, "status", None), "reason": getattr(e, "reason", "")},
            durationMs=_ms(t0),
        )
    # 其他 API 错误 => error
    return InspectItem(
        key=key,
        title=title,
        level="error",
        detail=f"K8s API 异常：{getattr(e, 'status', None)} {getattr(e, 'reason', '')}",
        suggestion="检查 apiserver 可达性、证书/凭据、以及集群是否正常。",
        evidence={"status": getattr(e, "status", None), "reason": getattr(e, "reason", "")},
        durationMs=_ms(t0),
    )


def check_prometheus_basic(enable: bool = True) -> InspectItem:
    """
    Prometheus 是否可用（可选项）
    - enable=False => skip
    - Prometheus 不可用 => warn（不影响整体巡检）
    """
    t0 = time.time()
    if not enable:
        return InspectItem(
            key="prometheus",
            title="Prometheus 采集状态",
            level="skip",
            detail="Prometheus 检查已关闭（INSPECT_ENABLE_PROM=false）",
            durationMs=_ms(t0),
        )
    if instant_value is None:
        return InspectItem(
            key="prometheus",
            title="Prometheus 采集状态",
            level="warn",
            detail="Prometheus client 未就绪（services.prometheus_client 不可导入），已跳过",
            suggestion="确认后端已配置 PROMETHEUS_BASE 且 services.prometheus_client 可正常导入。",
            durationMs=_ms(t0),
        )

    try:
        any_up = float(instant_value("sum(up)", 0.0) or 0.0)
        prom_ok = any_up > 0
        return InspectItem(
            key="prometheus",
            title="Prometheus 采集状态",
            level="ok" if prom_ok else "warn",
            detail="Prometheus 可用（up > 0）" if prom_ok else "Prometheus 不可用或无 up 数据（不会影响其他巡检项）",
            evidence={"sum_up": any_up},
            suggestion=None if prom_ok else "检查 PROMETHEUS_BASE、Prometheus target、网络连通性。",
            durationMs=_ms(t0),
        )
    except Exception as e:
        return InspectItem(
            key="prometheus",
            title="Prometheus 采集状态",
            level="warn",
            detail=f"Prometheus 查询失败（不影响整体巡检）：{e}",
            suggestion="检查 PROMETHEUS_BASE 配置、Prometheus 是否可达。",
            durationMs=_ms(t0),
        )


def check_nodes_ready() -> InspectItem:
    t0 = time.time()
    key = "nodes_ready"
    title = "节点状态（Ready/可调度）"
    need = "list nodes"

    try:
        v1 = get_core_v1()
        nodes = v1.list_node().items

        total = len(nodes)
        not_ready: List[str] = []
        scheduling_disabled: List[str] = []

        for n in nodes:
            name = getattr(n.metadata, "name", "") or "unknown"
            # Ready condition
            ready = False
            for c in (getattr(n.status, "conditions", None) or []):
                if getattr(c, "type", "") == "Ready" and getattr(c, "status", "") == "True":
                    ready = True
                    break
            if not ready:
                not_ready.append(name)

            # SchedulingDisabled
            unsched = bool(getattr(n.spec, "unschedulable", False))
            if unsched:
                scheduling_disabled.append(name)

        level = "ok"
        detail_parts = [f"节点总数：{total}"]
        if not_ready:
            level = "error"
            detail_parts.append(f"NotReady：{', '.join(not_ready)}")
        if scheduling_disabled:
            # 如果有 NotReady 已经 error；否则给 warn
            if level != "error":
                level = "warn"
            detail_parts.append(f"SchedulingDisabled：{', '.join(scheduling_disabled)}")

        return InspectItem(
            key=key,
            title=title,
            level=level,
            detail="；".join(detail_parts),
            suggestion=None
            if level == "ok"
            else "检查对应节点的 kubelet/containerd/flannel 状态与资源压力（Memory/Disk/PIDPressure）。",
            evidence={"total": total, "notReady": not_ready, "schedulingDisabled": scheduling_disabled},
            durationMs=_ms(t0),
        )
    except ApiException as e:
        return _api_exc_to_item(key=key, title=title, need_rbac=need, e=e, t0=t0)
    except Exception as e:
        return InspectItem(
            key=key,
            title=title,
            level="error",
            detail=f"检查失败：{e}",
            suggestion="检查后端 kubeconfig/incluster 配置是否正确。",
            durationMs=_ms(t0),
        )


def check_kube_system_core_pods() -> InspectItem:
    t0 = time.time()
    key = "kube_system_core_pods"
    title = "kube-system 核心组件 Pod 状态"
    need = "list pods (all namespaces) 或 list pods in kube-system"

    try:
        v1 = get_core_v1()
        pods = v1.list_namespaced_pod(namespace="kube-system").items

        # 你可以按需扩展关键组件
        keywords = ["coredns", "metrics-server", "local-path-provisioner", "flannel", "cilium"]
        bad: List[str] = []
        matched = 0

        for p in pods:
            name = getattr(p.metadata, "name", "") or ""
            phase = getattr(p.status, "phase", "") or ""
            # 只统计包含关键字的
            if any(k in name for k in keywords):
                matched += 1
                ready = True
                for cs in (getattr(p.status, "container_statuses", None) or []):
                    if not getattr(cs, "ready", False):
                        ready = False
                        break
                if phase not in ("Running", "Succeeded") or not ready:
                    bad.append(f"{name}({phase})")

        if matched == 0:
            return InspectItem(
                key=key,
                title=title,
                level="warn",
                detail="未匹配到预设关键组件（可能你的组件命名不同）",
                suggestion="你可以在 checks.py 里扩展 keywords 或改成 label 选择器。",
                evidence={"kubeSystemPods": len(pods), "matched": matched},
                durationMs=_ms(t0),
            )

        level = "ok" if not bad else "error"
        return InspectItem(
            key=key,
            title=title,
            level=level,
            detail="核心组件正常" if level == "ok" else f"异常组件：{', '.join(bad)}",
            suggestion=None
            if level == "ok"
            else "优先检查 coredns/metrics-server/CNI 相关 Pod 的事件与日志。",
            evidence={"matched": matched, "bad": bad},
            durationMs=_ms(t0),
        )
    except ApiException as e:
        return _api_exc_to_item(key=key, title=title, need_rbac=need, e=e, t0=t0)
    except Exception as e:
        return InspectItem(key=key, title=title, level="error", detail=f"检查失败：{e}", durationMs=_ms(t0))


def check_pods_abnormal(limit: int = 2000) -> InspectItem:
    t0 = time.time()
    key = "pods_abnormal"
    title = "业务 Pod 异常（CrashLoop/ImagePull/频繁重启）"
    need = "list pods (all namespaces)"

    try:
        v1 = get_core_v1()
        pods = v1.list_pod_for_all_namespaces(watch=False, limit=limit).items

        crash: List[str] = []
        imagepull: List[str] = []
        high_restart: List[str] = []

        for p in pods:
            ns = getattr(p.metadata, "namespace", "") or "default"
            name = getattr(p.metadata, "name", "") or "unknown"
            phase = getattr(p.status, "phase", "") or ""

            # 容器状态原因
            for cs in (getattr(p.status, "container_statuses", None) or []):
                restarts = int(getattr(cs, "restart_count", 0) or 0)
                if restarts >= 3:
                    high_restart.append(f"{ns}/{name}(restarts={restarts})")

                st = getattr(cs, "state", None)
                # waiting reason
                if st and getattr(st, "waiting", None):
                    reason = getattr(st.waiting, "reason", "") or ""
                    if reason in ("CrashLoopBackOff",):
                        crash.append(f"{ns}/{name}")
                    if reason in ("ImagePullBackOff", "ErrImagePull"):
                        imagepull.append(f"{ns}/{name}")

            # phase 兜底
            if phase in ("Failed", "Unknown"):
                crash.append(f"{ns}/{name}(phase={phase})")

        level = "ok"
        detail_parts: List[str] = []
        if crash:
            level = "error"
            detail_parts.append(f"Crash/Failed：{len(crash)}")
        if imagepull:
            level = "error"
            detail_parts.append(f"ImagePull：{len(imagepull)}")
        if high_restart and level != "error":
            level = "warn"
            detail_parts.append(f"高重启：{len(high_restart)}")

        if not detail_parts:
            detail_parts.append("未发现明显异常 Pod")

        return InspectItem(
            key=key,
            title=title,
            level=level,
            detail="；".join(detail_parts),
            suggestion=None
            if level == "ok"
            else "结合 events 与 logs 定位原因（镜像仓库/资源不足/配置错误/探针失败）。",
            evidence={
                "totalPods": len(pods),
                "crashSamples": crash[:20],
                "imagePullSamples": imagepull[:20],
                "highRestartSamples": high_restart[:20],
            },
            durationMs=_ms(t0),
        )
    except ApiException as e:
        return _api_exc_to_item(key=key, title=title, need_rbac=need, e=e, t0=t0)
    except Exception as e:
        return InspectItem(key=key, title=title, level="error", detail=f"检查失败：{e}", durationMs=_ms(t0))


def check_events_warnings(limit: int = 2000) -> InspectItem:
    t0 = time.time()
    key = "events"
    title = "集群事件（Warning/Error）"
    need = "list events (all namespaces)"

    try:
        v1 = get_core_v1()
        evs = v1.list_event_for_all_namespaces(limit=limit).items  # type: ignore

        warn = []
        for ev in evs:
            etype = getattr(ev, "type", "") or ""
            if etype in ("Warning", "Error"):
                ns = getattr(getattr(ev, "metadata", None), "namespace", "") or "default"
                name = getattr(getattr(ev, "involved_object", None), "name", "") or ""
                reason = getattr(ev, "reason", "") or ""
                msg = getattr(ev, "message", "") or ""
                warn.append(f"{ns}/{name} {reason}: {msg[:80]}")

        level = "ok" if len(warn) == 0 else ("warn" if len(warn) < 20 else "error")
        return InspectItem(
            key=key,
            title=title,
            level=level,
            detail="无 Warning/Error 事件" if not warn else f"Warning/Error 事件数：{len(warn)}",
            suggestion=None if not warn else "重点看 FailedScheduling / ImagePull / Unhealthy 等原因。",
            evidence={"samples": warn[:20], "totalEvents": len(evs), "badEvents": len(warn)},
            durationMs=_ms(t0),
        )
    except ApiException as e:
        return _api_exc_to_item(key=key, title=title, need_rbac=need, e=e, t0=t0)
    except Exception as e:
        return InspectItem(key=key, title=title, level="error", detail=f"检查失败：{e}", durationMs=_ms(t0))


def check_storage_basic() -> InspectItem:
    t0 = time.time()
    key = "storage"
    title = "存储（StorageClass / PV / PVC）"
    need = "list storageclasses / list persistentvolumes / list persistentvolumeclaims"

    try:
        v1 = get_core_v1()
        # sc 是 storage v1 api：在 CoreV1 里没有，需要 client.StorageV1Api
        from kubernetes import client  # 懒加载

        storage = client.StorageV1Api(api_client=getattr(v1, "api_client", None))
        scs = storage.list_storage_class().items  # type: ignore
        pvs = v1.list_persistent_volume().items  # type: ignore
        pvcs = v1.list_persistent_volume_claim_for_all_namespaces().items  # type: ignore

        pvc_bad: List[str] = []
        for pvc in pvcs:
            ns = getattr(pvc.metadata, "namespace", "") or "default"
            name = getattr(pvc.metadata, "name", "") or "unknown"
            phase = getattr(pvc.status, "phase", "") or ""
            if phase not in ("Bound",):
                pvc_bad.append(f"{ns}/{name}({phase})")

        pv_bad: List[str] = []
        for pv in pvs:
            name = getattr(pv.metadata, "name", "") or "unknown"
            phase = getattr(pv.status, "phase", "") or ""
            if phase in ("Failed", "Released") or (phase and phase not in ("Bound", "Available")):
                pv_bad.append(f"{name}({phase})")

        level = "ok"
        if pvc_bad or pv_bad:
            level = "warn" if len(pvc_bad) + len(pv_bad) < 10 else "error"

        return InspectItem(
            key=key,
            title=title,
            level=level,
            detail=f"SC:{len(scs)} PV:{len(pvs)} PVC:{len(pvcs)}" if level == "ok" else "存在异常存储绑定状态",
            suggestion=None if level == "ok" else "检查 provisioner、StorageClass 默认项、以及后端存储可用性。",
            evidence={
                "storageClasses": [getattr(x.metadata, "name", "") for x in scs][:20],
                "pvBad": pv_bad[:20],
                "pvcBad": pvc_bad[:20],
                "pvCount": len(pvs),
                "pvcCount": len(pvcs),
            },
            durationMs=_ms(t0),
        )
    except ApiException as e:
        # 这里可能是 list pv/pvc/sc 的 403
        return _api_exc_to_item(key=key, title=title, need_rbac=need, e=e, t0=t0)
    except Exception as e:
        return InspectItem(key=key, title=title, level="error", detail=f"检查失败：{e}", durationMs=_ms(t0))


def check_kube_dns_endpoints() -> InspectItem:
    t0 = time.time()
    key = "kube_dns"
    title = "kube-dns Endpoints（是否为空）"
    need = "get endpoints in kube-system"

    try:
        v1 = get_core_v1()
        ep = v1.read_namespaced_endpoints(name="kube-dns", namespace="kube-system")
        subsets = getattr(ep, "subsets", None) or []
        addrs = 0
        for ss in subsets:
            addrs += len(getattr(ss, "addresses", None) or [])
        level = "ok" if addrs > 0 else "error"
        return InspectItem(
            key=key,
            title=title,
            level=level,
            detail="kube-dns Endpoints 正常" if level == "ok" else "kube-dns Endpoints 为空（Service 可能不可用）",
            suggestion=None if level == "ok" else "检查 coredns Pod 状态与 kube-system 的网络插件是否正常。",
            evidence={"addresses": addrs},
            durationMs=_ms(t0),
        )
    except ApiException as e:
        return _api_exc_to_item(key=key, title=title, need_rbac=need, e=e, t0=t0)
    except Exception as e:
        return InspectItem(key=key, title=title, level="error", detail=f"检查失败：{e}", durationMs=_ms(t0))
