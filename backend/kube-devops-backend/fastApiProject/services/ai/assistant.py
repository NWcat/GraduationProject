# services/ai/assistant.py
from __future__ import annotations

from services.ai.schemas import AssistantChatReq, AssistantChatResp
from services.ai.llm_deepseek import DeepSeekClient
from services.ai.suggest import build_suggestions


def assistant_chat(req: AssistantChatReq) -> AssistantChatResp:
    """
    悬浮球 = 交互入口
    默认：先生成结构化建议/异常（确定性），再让 LLM 负责解释与步骤
    """
    ctx = req.context or {}
    target = ctx.get("target")  # node_cpu/node_mem/pod_cpu
    node = ctx.get("node")
    namespace = ctx.get("namespace")
    pod = ctx.get("pod")

    suggestions = None
    anomalies = None

    if target in ("node_cpu", "node_mem", "pod_cpu"):
        out = build_suggestions(
            target=target,
            node=node,
            namespace=namespace,
            pod=pod,
            history_minutes=int(ctx.get("history_minutes", 240)),
            horizon_minutes=int(ctx.get("horizon_minutes", 120)),
            step=int(ctx.get("step", 60)),
            threshold=float(ctx.get("threshold", 85.0)),
            sustain_minutes=int(ctx.get("sustain_minutes", 15)),
            use_llm=False,
        )
        suggestions = out["suggestions"]
        anomalies = out["anomalies"]

    llm = DeepSeekClient()

    # 不用 LLM：保底输出
    if (not req.use_llm) or (not llm.enabled()):
        lines = ["我已生成结构化建议。"]
        if suggestions:
            for s in suggestions.suggestions[:3]:
                lines.append(f"- [{s.severity}] {s.title}：{s.rationale}")
        if anomalies and anomalies.anomalies:
            lines.append(f"检测到异常点 {len(anomalies.anomalies)} 个（突发/偏离预测区间）。")
        return AssistantChatResp(reply="\n".join(lines), suggestions=suggestions, anomalies=anomalies)

    # 用 LLM：把上下文一起喂给模型
    brief = {
        "page": req.page,
        "context": ctx,
        "suggestions": suggestions.model_dump() if suggestions else None,
        "anomalies": anomalies.model_dump() if anomalies else None,
    }

    messages = [
        {"role": "system", "content": "你是云原生AIOps运维助手。回答要：简洁、可执行、分步骤。不要编造不存在的指标。"},
        {"role": "user", "content": f"用户问题：{req.message}\n\n系统上下文：{brief}"},
    ]
    reply = llm.chat(messages, temperature=0.2)

    return AssistantChatResp(reply=reply, suggestions=suggestions, anomalies=anomalies)
