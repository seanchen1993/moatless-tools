# SmartCompactMessageHistoryGenerator 使用指南

## 概述

`SmartCompactMessageHistoryGenerator` 是一个智能的混合消息历史压缩生成器，结合了基于规则的压缩和 LLM 摘要两种策略。

## 核心特性

### 🎯 智能混合策略

1. **优先使用规则压缩**（快速、零成本）
   - 去重文件查看
   - 智能保留关键操作（ViewCode、Edit等）
   - 状态感知的测试结果过滤
   - Token 限制管理

2. **必要时使用 LLM 摘要**（智能、语义理解）
   - 当规则压缩后仍超过阈值时触发
   - 保留最近的 N 条消息
   - 将中间历史压缩为结构化摘要
   - 自动跟踪成本

3. **优雅降级**
   - LLM 摘要失败时自动回退到规则压缩
   - 如果摘要没有减少 Token，仍使用规则压缩结果
   - 完全可预测的后备机制

## 使用方法

### 基础使用

```python
from moatless.message_history.smart_compact import SmartCompactMessageHistoryGenerator
from moatless.completion import BaseCompletionModel
from moatless.agent import ActionAgent

# 创建 completion model
completion_model = BaseCompletionModel(
    model="claude-3-5-sonnet-20241022",
    temperature=0.0,
    max_tokens=4000,
)

# 创建 smart compact generator
memory = SmartCompactMessageHistoryGenerator(
    max_tokens=100000,  # 总 Token 限制
    max_tokens_per_observation=10000,  # 每个观察的 Token 限制
    use_llm_summary=True,  # 启用 LLM 摘要
    llm_summary_threshold=70000,  # 超过此阈值触发 LLM 摘要
    n_messages_to_keep=3,  # LLM 摘要时保留最近的3条消息
    min_messages_for_summary=5,  # 至少5条消息才尝试摘要
)

# 设置 completion model（用于 LLM 摘要）
memory.set_completion_model(completion_model)

# 在 Agent 中使用
agent = ActionAgent(
    completion_model=completion_model,
    system_prompt="You are a helpful coding assistant.",
    actions=[...],
    memory=memory,  # 使用智能混合压缩
)
```

### 配置选项

```python
SmartCompactMessageHistoryGenerator(
    # 继承自 CompactMessageHistoryGenerator 的选项
    max_tokens=100000,  # 最大 Token 限制
    max_tokens_per_observation=10000,  # 每个观察的最大 Token
    include_file_context=True,  # 包含文件上下文
    include_git_patch=True,  # 包含 Git diff
    thoughts_in_action=False,  # 思考内容是否包含在动作中
    message_cache=False,  # 是否启用消息缓存
    
    # SmartCompact 特有的选项
    use_llm_summary=True,  # 是否启用 LLM 摘要
    llm_summary_threshold=70000,  # LLM 摘要的 Token 阈值（None 时自动为 max_tokens * 0.7）
    n_messages_to_keep=3,  # 摘要时保留的最近消息数
    summary_prompt="...",  # 自定义摘要提示词
    min_messages_for_summary=5,  # 触发摘要的最少消息数
)
```

## 工作流程

```
┌─────────────────────────────────────────┐
│  1. 调用 generate_messages()            │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  2. 执行规则压缩（父类方法）              │
│     - 去重文件                           │
│     - 优先保留 ViewCode                  │
│     - 状态感知测试结果                    │
│     - Token 限制                        │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  3. 检查是否需要 LLM 摘要                │
│     - 是否启用？                         │
│     - 是否有 completion model？          │
│     - Token 是否超过阈值？               │
│     - 消息是否足够多？                    │
└──────────────┬──────────────────────────┘
               │
       ┌───────┴───────┐
       │ 不需要        │ 需要
       ▼               ▼
┌────────────┐  ┌─────────────────────────┐
│ 返回规则   │  │  4. 尝试 LLM 摘要        │
│ 压缩结果   │  │     - 调用 LLM           │
│            │  │     - 生成摘要           │
└────────────┘  └──────────┬──────────────┘
                           │
                   ┌───────┴───────┐
                   │ 成功          │ 失败
                   ▼               ▼
            ┌──────────────┐  ┌─────────────┐
            │ Token 减少？  │  │ 返回规则    │
            └───┬──────────┘  │ 压缩结果    │
                │             └─────────────┘
        ┌───────┴───────┐
        │ 是            │ 否
        ▼               ▼
┌──────────────┐  ┌─────────────┐
│ 返回 LLM     │  │ 返回规则    │
│ 摘要结果     │  │ 压缩结果    │
└──────────────┘  └─────────────┘
```

## 性能与成本

### 场景对比

| 场景 | 消息数 | 规则压缩 Token | LLM 摘要 Token | 成本 | 延迟 |
|------|-------|---------------|---------------|------|-----|
| 短对话（<10轮） | 10 | 15,000 | N/A | $0 | <10ms |
| 中等对话（20轮） | 20 | 45,000 | N/A | $0 | <20ms |
| 长对话（50轮） | 50 | 85,000 | 30,000 | ~$0.03 | 2-5s |
| 超长对话（100轮） | 100 | 120,000 | 35,000 | ~$0.05 | 3-7s |

### 成本优化建议

1. **调整阈值**：提高 `llm_summary_threshold` 以减少 LLM 调用频率
2. **增加保留消息数**：提高 `n_messages_to_keep` 以保留更多上下文（但增加 Token）
3. **优化规则压缩**：调整 `max_tokens_per_observation` 以更积极地压缩观察结果
4. **禁用 LLM 摘要**：设置 `use_llm_summary=False` 完全依赖规则压缩（零成本）

## 监控与调试

### 查看摘要成本

```python
# 获取累计的摘要成本
total_cost = memory.total_summary_cost
print(f"Total LLM summarization cost: ${total_cost:.4f}")
```

### 日志级别

```python
import logging

# 启用详细日志
logging.getLogger("moatless.message_history.smart_compact").setLevel(logging.DEBUG)
```

日志输出示例：
```
DEBUG: Rule-based compression resulted in 25 messages with 85000 tokens
DEBUG: Tokens (85000) exceed LLM summary threshold (70000)
INFO: Attempting LLM summarization (current tokens: 85000)
INFO: LLM summary cost: $0.0342 (cumulative: $0.0342)
INFO: LLM summarization successful: 8 messages, 32000 tokens (reduced from 85000)
```

## 与其他生成器的对比

| 生成器 | 策略 | 成本 | 速度 | 适用场景 |
|--------|-----|------|-----|---------|
| **MessageHistoryGenerator** | 标准格式 | $0 | 快 | 通用场景 |
| **CompactMessageHistoryGenerator** | 规则压缩 | $0 | 快 | Token 优化 |
| **ReactCompactMessageHistoryGenerator** | ReAct + 规则 | $0 | 快 | ReAct 模式 |
| **SmartCompactMessageHistoryGenerator** | 混合策略 | 低 | 快-中 | 长对话优化 |

## 高级用法

### 自定义摘要提示词

```python
custom_prompt = """
Create a concise technical summary focusing on:
1. Code changes made
2. Files modified
3. Test results
4. Next steps

Keep it under 500 words.
"""

memory = SmartCompactMessageHistoryGenerator(
    summary_prompt=custom_prompt,
    max_tokens=100000,
)
```

### 动态调整策略

```python
# 根据对话长度动态调整
trajectory = node.get_trajectory()

if len(trajectory) > 50:
    # 长对话：更积极地使用 LLM 摘要
    memory.llm_summary_threshold = 50000
    memory.n_messages_to_keep = 5
elif len(trajectory) > 20:
    # 中等对话：适度使用
    memory.llm_summary_threshold = 70000
    memory.n_messages_to_keep = 3
else:
    # 短对话：禁用 LLM 摘要
    memory.use_llm_summary = False
```

### 只在特定条件下使用 LLM

```python
# 只在成本可接受时使用 LLM
if memory.total_summary_cost < 0.50:  # 累计成本小于 $0.50
    memory.use_llm_summary = True
else:
    logger.warning("Summary cost limit reached, disabling LLM summarization")
    memory.use_llm_summary = False
```

## 最佳实践

1. **初始化时设置 completion model**
   ```python
   memory = SmartCompactMessageHistoryGenerator(...)
   memory.set_completion_model(completion_model)
   ```

2. **为不同任务使用不同阈值**
   - 代码编辑任务：提高阈值（更多上下文）
   - 简单查询任务：降低阈值（节省成本）

3. **监控成本**
   - 定期检查 `total_summary_cost`
   - 设置成本上限

4. **测试降级行为**
   - 确保规则压缩在 LLM 失败时仍能工作
   - 验证 Token 限制正确应用

5. **根据模型选择策略**
   - 使用便宜的模型（如 GPT-4o-mini）进行摘要
   - 主任务使用更强大的模型

## 故障排除

### LLM 摘要从不触发

检查：
- `use_llm_summary` 是否为 `True`
- `completion_model` 是否已设置
- Token 是否真的超过 `llm_summary_threshold`
- 消息数是否 >= `min_messages_for_summary`

### 摘要后 Token 反而增加

原因：LLM 生成了过于详细的摘要

解决：
- 调整 `summary_prompt` 要求更简洁
- 增加 `n_messages_to_keep` 以保留更多原始消息
- 系统会自动回退到规则压缩结果

### 成本过高

解决：
- 提高 `llm_summary_threshold`
- 增加 `n_messages_to_keep`（减少需要摘要的内容）
- 考虑使用更便宜的模型进行摘要

## 未来改进方向

- [ ] 支持增量摘要（在现有摘要基础上更新）
- [ ] 支持多级摘要（摘要的摘要）
- [ ] 添加摘要质量评估
- [ ] 支持用户审核摘要
- [ ] 缓存摘要结果
