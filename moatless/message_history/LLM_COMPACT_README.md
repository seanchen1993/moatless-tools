# LLMCompactMessageHistoryGenerator

## 📋 概述

`LLMCompactMessageHistoryGenerator` 是**严格按照 TypeScript 实现思路**的智能压缩生成器。

这不是一个改进或修改版本，而是 **TypeScript `summarizeConversation` 函数的直接 Python 翻译**。

## 🎯 TypeScript 实现逻辑（完全遵循）

### TypeScript 原始逻辑

```typescript
export async function summarizeConversation(
    messages: ApiMessage[],
    ...
): Promise<SummarizeResponse> {
    // 1. 总是保留第一条消息（任务描述）
    const firstMessage = messages[0]
    
    // 2. 获取需要摘要的消息（排除最后 N 条）
    const messagesToSummarize = getMessagesSinceLastSummary(
        messages.slice(0, -N_MESSAGES_TO_KEEP)
    )
    
    // 3. 保留最后 N 条消息
    const keepMessages = messages.slice(-N_MESSAGES_TO_KEEP)
    
    // 4. 检查是否有最近的摘要
    const recentSummaryExists = keepMessages.some(message => message.isSummary)
    if (recentSummaryExists) {
        return error("condensed_recently")
    }
    
    // 5. 调用 LLM 生成摘要
    const summary = await handlerToUse.createMessage(SUMMARY_PROMPT, requestMessages)
    
    // 6. 创建摘要消息
    const summaryMessage = {
        role: "assistant",
        content: summary,
        isSummary: true,
    }
    
    // 7. 重构消息：[第一条, 摘要, 最后N条]
    const newMessages = [firstMessage, summaryMessage, ...keepMessages]
    
    // 8. 验证 Token 是否减少
    if (newContextTokens >= prevContextTokens) {
        return error("condense_context_grew")
    }
    
    return newMessages
}
```

### Python 实现（完全对应）

```python
async def generate_messages(self, node: Node, workspace: Workspace):
    # 1. 总是保留第一条消息（任务描述）
    first_message = node_messages[0] if node_messages else None
    
    # 2. 获取需要摘要的消息（排除最后 N 条）
    messages_to_summarize = self._get_messages_since_last_summary(
        node_messages[:-self.n_messages_to_keep]
    )
    
    # 3. 保留最后 N 条消息
    keep_messages = node_messages[-self.n_messages_to_keep:]
    
    # 4. 检查是否有最近的摘要
    recent_summary_exists = any(
        msg.assistant_message and "[SUMMARY]" in (msg.assistant_message or "")
        for msg in keep_messages
    )
    if recent_summary_exists:
        return await self._convert_node_messages_to_api_format(node_messages)
    
    # 5. 调用 LLM 生成摘要
    summary_text, cost = await self._call_llm_for_summary(messages_to_summarize)
    
    # 6. 创建摘要消息
    summary_message = NodeMessage(
        assistant_message=f"[SUMMARY]\n\n{summary_text}",
    )
    
    # 7. 重构消息：[第一条, 摘要, 最后N条]
    new_node_messages = []
    if first_message:
        new_node_messages.append(first_message)
    new_node_messages.append(summary_message)
    new_node_messages.extend(keep_messages)
    
    # 8. 验证 Token 是否减少
    if new_context_tokens >= prev_context_tokens:
        logger.warning("Summary did not reduce tokens, using original messages")
        return await self._convert_node_messages_to_api_format(node_messages)
    
    return await self._convert_node_messages_to_api_format(new_node_messages)
```

## 🔑 核心特点

### 1. 严格遵循 TypeScript

✅ **完全相同的常量**
```python
N_MESSAGES_TO_KEEP = 3  # 来自 TypeScript
MIN_CONDENSE_THRESHOLD = 5
MAX_CONDENSE_THRESHOLD = 100
```

✅ **完全相同的 SUMMARY_PROMPT**
```python
SUMMARY_PROMPT = """
Your task is to create a detailed summary...
(与 TypeScript 完全相同，逐字逐句)
"""
```

✅ **完全相同的逻辑流程**
- 保留首条消息
- 保留最后 N 条
- 中间用 LLM 摘要
- 验证 Token 减少

### 2. 与 compact.py 的关键区别

| 特性 | compact.py | llm_compact.py (本实现) |
|------|-----------|------------------------|
| **ViewCode 处理** | 特殊处理（总是保留） | 一视同仁 |
| **其他动作处理** | Token 计算 + 手动选择 | 一视同仁 |
| **压缩策略** | 规则：去重、过滤 | LLM：智能摘要 |
| **Token 管理** | 手动计算和跳过 | LLM 自动压缩 |
| **摘要位置** | 无固定结构 | [首条, 摘要, 最后N条] |

### 3. 所有动作一视同仁

```python
# compact.py 的做法（区分处理）
if isinstance(action_step.action, ViewCodeArgs):
    # 特殊处理：总是包含
    actions.append(action_step.action)
else:
    # 其他动作：检查 Token 限制
    if total_tokens + message_tokens <= self.max_tokens:
        actions.append(action_step.action)
```

```python
# llm_compact.py 的做法（一视同仁）
for action_step in previous_node.action_steps:
    if not action_step.observation:
        continue
    
    # 所有动作都同等对待
    actions.append(action_step.action)
    observations.append(action_step.observation.message or "No output found.")
```

## 🚀 使用方法

### 基础使用

```python
from moatless.message_history.llm_compact import LLMCompactMessageHistoryGenerator
from moatless.completion import BaseCompletionModel
from moatless.agent import ActionAgent

# 1. 创建 completion model
completion_model = BaseCompletionModel(
    model="claude-3-5-sonnet-20241022",
    temperature=0.0,
)

# 2. 创建 LLM Compact generator
memory = LLMCompactMessageHistoryGenerator(
    n_messages_to_keep=3,  # TypeScript: N_MESSAGES_TO_KEEP
    min_messages_for_summary=5,  # TypeScript: MIN_CONDENSE_THRESHOLD
)

# 3. 设置 completion model（必须）
memory.set_completion_model(completion_model)

# 4. 在 Agent 中使用
agent = ActionAgent(
    completion_model=completion_model,
    memory=memory,  # ← 使用 TypeScript 风格的 LLM 压缩
    ...
)
```

### 配置选项

```python
LLMCompactMessageHistoryGenerator(
    # TypeScript 对应的配置
    n_messages_to_keep=3,  # N_MESSAGES_TO_KEEP
    min_messages_for_summary=5,  # MIN_CONDENSE_THRESHOLD
    summary_prompt=SUMMARY_PROMPT,  # 自定义摘要提示词
    
    # 继承自 compact.py 的配置
    max_tokens=None,  # 不使用（LLM 自动处理）
    include_file_context=True,
    include_git_patch=True,
    thoughts_in_action=False,
)
```

## 📊 行为示例

### 场景：10 条消息的对话

```
原始消息:
1. [用户] 请修复 bug
2. [助手] 我会帮你
3. [动作] ViewCode(main.py)
4. [观察] def main(): ...
5. [动作] EditFile(main.py)
6. [观察] 已编辑
7. [动作] RunTests
8. [观察] 2 passed, 1 failed
9. [动作] ViewCode(test.py)
10. [观察] def test_foo(): ...

LLM Compact 处理:
↓
压缩后:
1. [用户] 请修复 bug                    ← 首条（保留）
2. [助手] [SUMMARY]                     ← LLM 摘要
   用户要求修复 bug。我查看了 main.py，
   进行了编辑，运行测试发现 1 个失败...
8. [观察] 2 passed, 1 failed            ← 最后 3 条（保留）
9. [动作] ViewCode(test.py)
10. [观察] def test_foo(): ...
```

## 🔍 与 TypeScript 的完全对应

### TypeScript 代码片段
```typescript
const firstMessage = messages[0]
const messagesToSummarize = messages.slice(0, -N_MESSAGES_TO_KEEP)
const keepMessages = messages.slice(-N_MESSAGES_TO_KEEP)
```

### Python 对应代码
```python
first_message = node_messages[0] if node_messages else None
messages_to_summarize = node_messages[:-self.n_messages_to_keep]
keep_messages = node_messages[-self.n_messages_to_keep:]
```

### TypeScript 错误处理
```typescript
if (newContextTokens >= prevContextTokens) {
    const error = t("common:errors.condense_context_grew")
    return { ...response, cost, error }
}
```

### Python 对应错误处理
```python
if new_context_tokens >= prev_context_tokens:
    logger.warning(
        f"Summary did not reduce tokens ({new_context_tokens} >= {prev_context_tokens}), "
        "using original messages"
    )
    return await self._convert_node_messages_to_api_format(node_messages)
```

## ⚠️ 重要说明

### 必须设置 Completion Model

```python
memory = LLMCompactMessageHistoryGenerator()
memory.set_completion_model(completion_model)  # ← 必须调用
```

如果未设置，会自动降级到父类实现：
```python
if not self._completion_model:
    logger.warning("No completion model set, falling back to parent implementation")
    return await super().generate_messages(node, workspace)
```

### 成本追踪

```python
# 查看累计成本
total_cost = memory.total_summary_cost
print(f"LLM 摘要成本: ${total_cost:.4f}")
```

### 何时触发摘要

只有满足以下条件才会触发 LLM 摘要：
1. ✅ 设置了 completion model
2. ✅ 消息数 > n_messages_to_keep + 1
3. ✅ 没有最近的摘要
4. ✅ 可摘要的消息 > 1

## 📝 日志输出

启用详细日志：
```python
import logging
logging.getLogger("moatless.message_history.llm_compact").setLevel(logging.DEBUG)
```

示例输出：
```
DEBUG: Processing 25 previous nodes
DEBUG: Collected 25 node messages (all actions treated equally)
DEBUG: Calling LLM with 22 messages for summarization
DEBUG: LLM summary generated: 1523 chars, cost: $0.0312
INFO:  LLM summarization successful: 6 messages, 32145 tokens (reduced from 87234), cost: $0.0312
```

## 🎯 设计原则

### 1. 忠实于 TypeScript

这个实现的目标是**完全复制 TypeScript 的行为**，而不是改进它。

如果 TypeScript 的实现有问题，这个 Python 版本也会有相同的问题。这是有意为之的。

### 2. 不擅自优化

即使我们知道某些地方可以优化（如去重、状态感知等），我们也**不添加这些优化**。

如果需要优化版本，请使用 `SmartCompactMessageHistoryGenerator`。

### 3. 所有动作平等

不区分 ViewCode、EditFile、RunTests 等，所有动作都：
- 收集到消息列表
- 参与 LLM 摘要
- 或被保留在最后 N 条中

## 📚 对比总结

| 实现 | 策略 | 优点 | 缺点 |
|------|-----|------|-----|
| **TypeScript** | 固定窗口 + LLM | 简单、语义理解 | 总是有成本、可能失败 |
| **Python compact.py** | 规则压缩 | 快速、零成本 | 无语义理解 |
| **Python llm_compact.py** | TypeScript 移植 | 与 TypeScript 一致 | 继承 TypeScript 的限制 |
| **Python smart_compact.py** | 混合策略 | 两者优点 | 更复杂 |

## 🚀 何时使用

### 使用 LLMCompact 的场景

✅ 需要与 TypeScript 实现完全一致的行为  
✅ 已经在使用 TypeScript 版本，想迁移到 Python  
✅ 信任 TypeScript 的设计决策  
✅ 不需要规则压缩的优化

### 不使用 LLMCompact 的场景

❌ 想要零成本压缩 → 使用 `CompactMessageHistoryGenerator`  
❌ 想要混合策略 → 使用 `SmartCompactMessageHistoryGenerator`  
❌ 需要区分处理不同动作 → 使用 `CompactMessageHistoryGenerator`

---

**这是 TypeScript `summarizeConversation` 的忠实 Python 翻译。** 🎯
