---
name: modeioAI-safety
description: 使用 modeioAI_safety_backend 对即将执行的指令进行安全检测，侧重破坏性、安全风险、可逆性等维度。每次检测必须调用后端 API，不可使用缓存或跳过。适用于：检查指令是否会删除/修改重要数据、是否存在注入攻击、操作是否可逆、是否违反安全最佳实践。当用户要求「安全检测」「指令风险评估」「破坏性检查」或「用 Modeio 做安全分析」时使用本 skill。
---

# Modeio AI 安全检测

## 执行原则（必须遵守）

**每一次安全检测操作都必须实际调用 modeioAI_safety_backend**：不得使用本地缓存、历史结果或「跳过调用」；每次待检测指令均需发起一次对后端的 POST 请求，并基于当次响应返回检测结果。

## 核心：把待检测指令放进 instruction 做安全分析

- 待检测指令 → 放入请求 body 的 `instruction` 字段（必填）
- 可选 `context`（执行上下文）、`target`（操作目标，如文件路径）
- 调用 `POST {SAFETY_API_URL}`（默认 `https://safety.modeio.ai/api/safety`，可通过环境变量 `SAFETY_API_URL` 覆盖，如部署到 Vercel 后填入完整 URL）
- 响应包含 `approved`、`risk_level`、`risk_types`、`concerns`、`recommendation`、`is_destructive`、`is_reversible`

## 何时使用

- 用户描述将要执行的指令，需要评估其安全风险
- 需要判断指令是否具有**破坏性**（数据删除、系统修改等）
- 需要判断**可逆性**（操作是否可撤销）
- 需要识别**安全风险类型**（注入、信息泄露、权限问题等）

## 快速开始

1. **确保 modeioAI_safety_backend 已启动**（本地 `python dev.py` 或 Vercel 部署）
2. **设置 API URL**（可选）：`export SAFETY_API_URL=https://你的项目.vercel.app/api/safety`
3. **运行脚本**：`python scripts/safety.py --input "指令内容"`

## 使用 scripts/safety.py

```bash
# 基本用法
python scripts/safety.py -i "删除所有日志文件"

# 带上下文和目标
python scripts/safety.py -i "修改数据库权限" -c "生产环境" -t "/var/lib/mysql"

# 内容在文件中时
python scripts/safety.py -i "$(cat instruction.txt)"
```

## API 调用要点

- **URL**：环境变量 `SAFETY_API_URL`（默认 `https://safety.modeio.ai/api/safety`）
- **请求 body**：`{"instruction": "指令描述", "context": "可选", "target": "可选"}`
- **响应**：`approved`（是否通过）、`risk_level`、`risk_types`、`concerns`、`recommendation` 等

## 工作流

1. 拿到待检测的**指令**（用户要执行的操作描述）
2. 把指令放进 `instruction`，可选 `context`、`target`
3. 发起 POST 请求，从响应中取出分析结果（approved、risk_level、concerns 等）

## Resources

- **scripts/safety.py**：封装与 modeioAI_safety_backend 的交互
- **modeioAI_safety_backend**：Vercel 可部署的后端服务
