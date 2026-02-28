#!/usr/bin/env python3
"""
Modeio AI 安全检测脚本：调用 modeioAI_safety_backend 对指令进行安全分析。
侧重破坏性、安全风险、可逆性等维度的检测。
"""

import argparse
import json
import os
import sys

import requests

# 后端 API URL，可通过环境变量 SAFETY_API_URL 覆盖
URL = os.environ.get("SAFETY_API_URL", "https://safety.modeio.ai/api/safety")


def detect_safety(instruction: str, context: str = None, target: str = None) -> dict:
    """
    调用 modeioAI_safety_backend，返回完整响应 JSON。
    包含 approved、risk_level、risk_types、concerns、recommendation 等。
    """
    payload = {"instruction": instruction}
    if context:
        payload["context"] = context
    if target:
        payload["target"] = target
    resp = requests.post(URL, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()


def main():
    parser = argparse.ArgumentParser(
        description="使用 modeioAI_safety_backend 对指令进行安全检测（破坏性、风险等级、可逆性等）"
    )
    parser.add_argument("-i", "--input", type=str, required=True, help="待检测的指令或操作描述")
    parser.add_argument("-c", "--context", type=str, default=None, help="执行上下文（可选）")
    parser.add_argument("-t", "--target", type=str, default=None, help="操作目标，如文件路径（可选）")
    args = parser.parse_args()

    raw_input = args.input

    if not raw_input or not raw_input.strip():
        print("Error: 输入为空", file=sys.stderr)
        sys.exit(1)

    try:
        result = detect_safety(
            instruction=raw_input,
            context=args.context,
            target=args.target,
        )
    except requests.RequestException as e:
        print(f"Error: API 请求失败: {e}", file=sys.stderr)
        sys.exit(1)

    if result.get("error"):
        print(f"Error: {result['error']}", file=sys.stderr)
        print(json.dumps(result, indent=2, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    # 兼容旧格式：success=True, data=完整结果
    output = {"success": True, "data": result}

    print("Status: success", file=sys.stderr)
    print(json.dumps(output["data"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
