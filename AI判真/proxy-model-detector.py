#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 中转站模型真实性检测工具 (Proxy Model Detector)
================================================================================

用途：
    检测第三方 API 中转站（代理服务）提供的模型是否为真实模型，
    还是用廉价模型"套壳"冒充高端模型。

原理：
    通过 8 项自动化测试，从多个维度评估模型的真实性：
    1. 知识截止日期  — 真模型能明确回答训练数据截止时间
    2. 数学推理      — 高端模型能正确求解多步骤数学题
    3. 代码生成      — 检查代码质量和算法选择是否符合高端模型水平
    4. 多语言能力    — 高端模型具备优秀的多语言翻译能力
    5. 逻辑推理      — 三段论传递性推理，真模型必对
    6. 自我认知      — 模型是否知道自己的名称和厂商
    7. 响应速度      — 过快可能是缓存/小模型，过慢可能排队严重
    8. 返回模型名    — API 返回的 model 字段是否与请求一致

评分标准：
    每项测试 0~1 分，总分 0~8 分。
    🟢 ≥ 75%（6/8）  — 大概率是真模型
    🟡 50%~75%       — 存在疑点，建议进一步测试
    🔴 < 50%         — 大概率是假模型/套壳

依赖：
    pip install requests

用法：
    python proxy-model-detector.py --base-url <URL> --api-key <KEY> --model <MODEL_NAME>

示例：
    # 测试中转站的 grok-4.5
    python proxy-model-detector.py \\
        --base-url https://rsxermu666.cn/openai/v1 \\
        --api-key sk-xxxxxxxx \\
        --model grok-4.5

    # 测试 OpenAI 官方（作为基准对比）
    python proxy-model-detector.py \\
        --base-url https://api.openai.com/v1 \\
        --api-key sk-xxxxxxxx \\
        --model gpt-4o

注意事项：
    - Windows 环境如遇 emoji 编码错误，请设置环境变量：
      PowerShell:  $env:PYTHONIOENCODING = "utf-8"
      CMD:         set PYTHONIOENCODING=utf-8
    - 每次测试约需 3~5 分钟（8 次 API 调用，含网络延迟）
    - 测试结果会生成 JSON 报告文件 proxy-detection-report-<timestamp>.json
    - 本工具仅提供参考，不保证 100% 准确判断
    - 建议对同一中转站多次测试，取平均结果

输出文件：
    proxy-detection-report-<unix_timestamp>.json — 包含每项测试的详细结果
================================================================================
"""

import argparse
import json
import time
import sys
from datetime import datetime

# 第三方依赖：requests 用于 HTTP 调用
try:
    import requests
except ImportError:
    print("缺少依赖：requests。请运行 pip install requests 后重试。")
    sys.exit(1)


# ==============================================================================
# 核心函数：调用 OpenAI 兼容 API
# ==============================================================================
def call_api(base_url, api_key, model, prompt, temperature=0.0, max_tokens=2048):
    """
    调用 OpenAI 兼容的 /chat/completions 接口。

    参数:
        base_url    — API 基础地址（如 https://api.openai.com/v1）
        api_key     — API 密钥
        model       — 模型名称（如 grok-4.5）
        prompt      — 用户提示词
        temperature — 采样温度，默认 0（确定性输出，便于对比）
        max_tokens  — 最大生成 token 数

    返回:
        成功时: {"content", "model", "usage", "elapsed", "finish_reason"}
        失败时: {"error", "elapsed"}
    """
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    start = time.time()
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=120)
        elapsed = time.time() - start
        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}", "body": resp.text[:500], "elapsed": elapsed}
        data = resp.json()
        return {
            "content": data["choices"][0]["message"]["content"],
            "model": data.get("model", "N/A"),
            "usage": data.get("usage", {}),
            "elapsed": elapsed,
            "finish_reason": data["choices"][0].get("finish_reason", "N/A"),
        }
    except Exception as e:
        return {"error": str(e), "elapsed": time.time() - start}


# ==============================================================================
# 辅助函数：打印单次 API 调用结果
# ==============================================================================
def print_result(r):
    """格式化打印 API 调用结果，截断过长内容。"""
    if "error" in r:
        print(f"  [ERROR] {r['error']}")
        if "body" in r:
            print(f"  响应体: {r['body'][:200]}")
        print(f"  耗时: {r.get('elapsed', 0):.2f}s")
        return

    content = r.get("content", "")
    print(f"  返回模型: {r.get('model', 'N/A')}")
    print(f"  耗时: {r['elapsed']:.2f}s")
    print(f"  Token 用量: {r.get('usage', {})}")
    print(f"  完成原因: {r.get('finish_reason', 'N/A')}")
    # 预览前 300 字符，避免刷屏
    preview = content[:300]
    if len(content) > 300:
        preview += "..."
    print(f"  回复预览:\n{preview}")


# ==============================================================================
# 主测试流程：8 项检测
# ==============================================================================
def run_tests(base_url, api_key, model):
    """
    依次执行 8 项测试，收集评分和原始结果。
    每项测试满分 1 分，总满分 8 分。
    """
    results = []
    total_score = 0
    max_score = 0

    # ──────────────────────────────────────────────────────────────────────────
    # 测试 1: 知识截止日期
    # 真模型通常能明确回答训练数据截止时间；套壳小模型往往不知道或回避。
    # ──────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("测试 1/8: 知识截止日期检测")
    print("=" * 60)
    r = call_api(base_url, api_key, model,
                 "What is your knowledge cutoff date? Answer in one sentence.")
    print_result(r)
    if "error" not in r:
        content = r["content"].lower()
        # 检查是否包含截止日期相关关键词
        if any(kw in content for kw in ["cutoff", "截止", "knowledge", "训练", "train", "data"]):
            # 进一步检查是否提到具体年份
            if any(kw in content for kw in ["2025", "2026", "2024"]):
                score, reason = 1, "能明确回答知识截止日期"
            else:
                score, reason = 0.5, "回答了截止日期但年份不明确"
        else:
            score, reason = 0, "无法回答知识截止日期（可疑）"
    else:
        score, reason = 0, f"API 错误: {r['error']}"
    results.append(("知识截止日期", score, reason, r))
    total_score += score
    max_score += 1

    # ──────────────────────────────────────────────────────────────────────────
    # 测试 2: 数学推理
    # 两车相向而行问题，正确答案约 334 km。
    # 廉价模型常犯忽略延迟出发的错误，得出 420 km。
    # 公式: 60(t+1) + 80t = 700 → t = 4.571h, 距 A = 60 × 5.571 ≈ 334.3 km
    # ──────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("测试 2/8: 数学推理能力")
    print("=" * 60)
    r = call_api(base_url, api_key, model,
                 "A train leaves station A at 60 km/h. Another train leaves station B at 80 km/h. "
                 "The distance between A and B is 700 km. Train B leaves 1 hour after train A. "
                 "At what time (distance from A) do they meet? Show your calculation step by step.")
    print_result(r)
    if "error" not in r:
        content = r["content"]
        if "334" in content or "335" in content or "334.3" in content:
            score, reason = 1, "数学计算正确（334-335 km）"
        elif "420" in content:
            score, reason = 0, "数学计算错误（常见错误答案 420）"
        else:
            score, reason = 0.3, "数学计算结果不明确"
    else:
        score, reason = 0, f"API 错误: {r['error']}"
    results.append(("数学推理", score, reason, r))
    total_score += score
    max_score += 1

    # ──────────────────────────────────────────────────────────────────────────
    # 测试 3: 代码生成
    # 括号匹配是经典栈问题。高端模型会用栈 + 字典映射；小模型可能用计数器。
    # ──────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("测试 3/8: 代码生成质量")
    print("=" * 60)
    r = call_api(base_url, api_key, model,
                 "Write a Python function `is_balanced(s: str) -> bool` that checks if parentheses, "
                 "brackets, and braces are balanced. Include edge cases. No explanation, just code.")
    print_result(r)
    if "error" not in r:
        content = r["content"]
        has_stack = "stack" in content.lower()  # 使用栈 = 标准解法
        has_def = "def is_balanced" in content  # 函数定义正确
        if has_def and has_stack:
            score, reason = 1, "代码结构正确（使用栈）"
        elif has_def:
            score, reason = 0.5, "有函数定义但可能缺少栈逻辑"
        else:
            score, reason = 0, "代码质量差"
    else:
        score, reason = 0, f"API 错误: {r['error']}"
    results.append(("代码生成", score, reason, r))
    total_score += score
    max_score += 1

    # ──────────────────────────────────────────────────────────────────────────
    # 测试 4: 多语言能力
    # 日语翻译 + 逐词解释。高端模型能提供假名 + 罗马音 + 逐词解析。
    # 廉价模型通常只能给出简单翻译，缺乏语言学细节。
    # ──────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("测试 4/8: 多语言能力")
    print("=" * 60)
    r = call_api(base_url, api_key, model,
                 "Translate to Japanese (romaji + kanji): 'The quick brown fox jumps over the lazy dog.' "
                 "Then explain each word.")
    print_result(r)
    if "error" not in r:
        content = r["content"]
        # 检查是否包含平假名/片假名
        has_japanese = any(c in content for c in "あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをん")
        # 检查是否包含罗马音关键词
        has_romaji = any(word in content.lower() for word in ["kitsu", "kitsune", "taiketsu", "nobi", "jump", "fox"])
        if has_japanese and has_romaji:
            score, reason = 1, "日语翻译质量好（含假名和罗马音）"
        elif has_japanese:
            score, reason = 0.7, "有日语但缺少罗马音"
        else:
            score, reason = 0.2, "多语言能力差（可疑）"
    else:
        score, reason = 0, f"API 错误: {r['error']}"
    results.append(("多语言能力", score, reason, r))
    total_score += score
    max_score += 1

    # ──────────────────────────────────────────────────────────────────────────
    # 测试 5: 逻辑推理
    # 经典三段论传递性：A⊆B, B⊆C → A⊆C。
    # 这是高端模型必对题，廉价模型可能答错或无法解释推理过程。
    # ──────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("测试 5/8: 逻辑推理")
    print("=" * 60)
    r = call_api(base_url, api_key, model,
                 "If all Bloops are Razzies and all Razzies are Lazzies, "
                 "then are all Bloops definitely Lazzies? Explain your reasoning in 2-3 sentences.")
    print_result(r)
    if "error" not in r:
        content = r["content"].lower()
        if "yes" in content and ("transit" in content or "传递" in content or "all" in content):
            score, reason = 1, "逻辑推理正确（三段论）"
        elif "yes" in content:
            score, reason = 0.7, "答案正确但推理不清晰"
        else:
            score, reason = 0, "逻辑推理错误"
    else:
        score, reason = 0, f"API 错误: {r['error']}"
    results.append(("逻辑推理", score, reason, r))
    total_score += score
    max_score += 1

    # ──────────────────────────────────────────────────────────────────────────
    # 测试 6: 模型自我认知
    # 问模型自己的名称、厂商、参数量、上下文窗口。
    # 真模型通常能正确回答厂商信息；套壳模型可能露馅（说出真实身份）。
    # 注意：自我认知可以被 system prompt 覆盖，所以此项仅供参考。
    # ──────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("测试 6/8: 模型自我认知")
    print("=" * 60)
    r = call_api(base_url, api_key, model,
                 "What is your model name and who created you? Be specific. "
                 "What is your parameter count and context window size?")
    print_result(r)
    if "error" not in r:
        content = r["content"].lower()
        # 检查是否声称是 xAI/Grok（与请求的模型名一致）
        claims_grok = "grok" in content
        claims_xai = "x.ai" in content or "xai" in content
        knows_params = "parameter" in content or "参数" in content or "billion" in content or "B" in content
        knows_context = "context" in content or "token" in content or "上下文" in content
        if claims_grok and claims_xai:
            if knows_params and knows_context:
                score, reason = 1, "自我认知一致（Grok + xAI + 参数信息）"
            else:
                score, reason = 0.7, "声称是 Grok 但参数信息不明确"
        else:
            score, reason = 0.2, "自我认知异常（未声称是 Grok/xAI）"
    else:
        score, reason = 0, f"API 错误: {r['error']}"
    results.append(("自我认知", score, reason, r))
    total_score += score
    max_score += 1

    # ──────────────────────────────────────────────────────────────────────────
    # 测试 7: 响应速度
    # 高端大模型生成速度通常在 5~30 秒（视 prompt 长度和输出长度）。
    # < 1 秒 → 可能是缓存或小模型（可疑）
    # 1~5 秒 → 正常
    # 5~30 秒 → 可能是大模型或中转站排队
    # > 30 秒 → 服务不稳定（中转站延迟严重）
    # ──────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("测试 7/8: 响应速度检测")
    print("=" * 60)
    r = call_api(base_url, api_key, model,
                 "Write a haiku about artificial intelligence.", temperature=0.7, max_tokens=100)
    print_result(r)
    if "error" not in r:
        elapsed = r["elapsed"]
        if elapsed < 1:
            score, reason = 0.3, f"响应过快（{elapsed:.2f}s）— 可能是缓存或小模型"
        elif elapsed < 5:
            score, reason = 1, f"响应速度正常（{elapsed:.2f}s）"
        elif elapsed < 30:
            score, reason = 0.7, f"响应较慢（{elapsed:.2f}s）— 可能是排队或大模型"
        else:
            score, reason = 0.3, f"响应过慢（{elapsed:.2f}s）— 服务不稳定"
    else:
        score, reason = 0, f"API 错误: {r['error']}"
    results.append(("响应速度", score, reason, r))
    total_score += score
    max_score += 1

    # ──────────────────────────────────────────────────────────────────────────
    # 测试 8: API 返回模型名
    # OpenAI 兼容 API 的响应中通常包含 "model" 字段。
    # 如果中转站返回的模型名与请求不一致，说明可能在转发到其他模型。
    # ──────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("测试 8/8: API 返回模型名检测")
    print("=" * 60)
    r = call_api(base_url, api_key, model, "Say hello in 3 languages.")
    print_result(r)
    if "error" not in r:
        returned_model = r.get("model", "N/A")
        if model.lower() in returned_model.lower():
            score, reason = 1, f"返回模型名匹配: {returned_model}"
        elif returned_model == "N/A":
            score, reason = 0.5, "API 未返回模型名"
        else:
            score, reason = 0, f"返回模型名不匹配: 请求={model}, 返回={returned_model}"
    else:
        score, reason = 0, f"API 错误: {r['error']}"
    results.append(("模型名检测", score, reason, r))
    total_score += score
    max_score += 1

    # ==============================================================================
    # 汇总报告
    # ==============================================================================
    print("\n" + "=" * 60)
    print("[检测报告]")
    print("=" * 60)
    print(f"目标: {base_url}")
    print(f"模型: {model}")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    for name, score, reason, r in results:
        # 用符号直观表示通过/可疑/失败
        status = "[OK]" if score >= 0.7 else "[?]" if score >= 0.4 else "[X]"
        print(f"  {status} {name}: {score:.1f}/1.0 — {reason}")

    percentage = (total_score / max_score * 100) if max_score > 0 else 0
    print(f"\n  总分: {total_score:.1f}/{max_score} ({percentage:.0f}%)")

    # 根据总分给出结论
    if percentage >= 75:
        verdict = "[GOOD] 大概率是真模型"
    elif percentage >= 50:
        verdict = "[WARN] 存在疑点，建议进一步测试"
    else:
        verdict = "[BAD] 大概率是假模型/套壳"

    print(f"  结论: {verdict}")
    print()

    # ==============================================================================
    # 输出 JSON 详细报告
    # ==============================================================================
    report = {
        "target": base_url,
        "model": model,
        "timestamp": datetime.now().isoformat(),
        "total_score": total_score,
        "max_score": max_score,
        "percentage": round(percentage, 1),
        "verdict": verdict,
        "tests": [
            {
                "name": name,
                "score": score,
                "reason": reason,
                "response_preview": (r.get("content", r.get("error", "")) or "")[:200],
                "elapsed": r.get("elapsed", 0),
                "returned_model": r.get("model", "N/A"),
                "usage": r.get("usage", {}),
            }
            for name, score, reason, r in results
        ],
    }

    report_path = f"proxy-detection-report-{int(time.time())}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"详细报告已保存: {report_path}")

    return percentage >= 75


# ==============================================================================
# 命令行入口
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(
        description="中转站模型真实性检测工具 — 检测第三方 API 代理是否使用真实模型",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 测试中转站的 grok-4.5
  python proxy-model-detector.py --base-url https://rsxermu666.cn/openai/v1 --api-key sk-xxx --model grok-4.5

  # 测试 OpenAI 官方（作为基准对比）
  python proxy-model-detector.py --base-url https://api.openai.com/v1 --api-key sk-xxx --model gpt-4o

  # Windows 如遇编码错误，先执行：
  #   PowerShell:  $env:PYTHONIOENCODING = "utf-8"
  #   CMD:         set PYTHONIOENCODING=utf-8
        """,
    )
    parser.add_argument("--base-url", required=True,
                        help="API base URL（如 https://rsxermu666.cn/openai/v1）")
    parser.add_argument("--api-key", required=True,
                        help="API 密钥")
    parser.add_argument("--model", required=True,
                        help="要测试的模型名称（如 grok-4.5）")
    args = parser.parse_args()

    print(f"[检测开始] {args.model} @ {args.base_url}")
    run_tests(args.base_url, args.api_key, args.model)


if __name__ == "__main__":
    main()
