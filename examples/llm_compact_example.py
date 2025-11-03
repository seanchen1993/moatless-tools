"""
LLMCompactMessageHistoryGenerator 使用示例

这个示例展示如何使用严格按照 TypeScript 实现的 LLM 压缩生成器。
"""

from moatless.agent import ActionAgent
from moatless.completion import BaseCompletionModel
from moatless.message_history.llm_compact import LLMCompactMessageHistoryGenerator
from moatless.actions import (
    ViewCode,
    EditFile,
    SemanticSearch,
    Finish,
)


def example_basic_usage():
    """基础使用示例 - TypeScript 风格"""
    print("=== 基础使用示例 ===\n")
    
    # 1. 创建 completion model
    completion_model = BaseCompletionModel(
        model="claude-3-5-sonnet-20241022",
        temperature=0.0,
        max_tokens=4000,
    )
    
    # 2. 创建 LLM Compact generator（TypeScript 风格）
    memory = LLMCompactMessageHistoryGenerator(
        n_messages_to_keep=3,  # TypeScript: N_MESSAGES_TO_KEEP
        min_messages_for_summary=5,  # TypeScript: MIN_CONDENSE_THRESHOLD
    )
    
    # 3. 设置 completion model（必须）
    memory.set_completion_model(completion_model)
    
    # 4. 创建 Agent
    agent = ActionAgent(
        agent_id="llm-compact-agent",
        completion_model=completion_model,
        system_prompt="You are a helpful coding assistant.",
        actions=[
            ViewCode(),
            SemanticSearch(),
            EditFile(),
            Finish(),
        ],
        memory=memory,  # ← 使用 TypeScript 风格的 LLM 压缩
    )
    
    print(f"✓ Agent created with LLM Compact memory")
    print(f"  - Messages to keep: {memory.n_messages_to_keep}")
    print(f"  - Min messages for summary: {memory.min_messages_for_summary}")
    print()


def example_typescript_constants():
    """展示 TypeScript 常量的使用"""
    print("=== TypeScript 常量 ===\n")
    
    from moatless.message_history.llm_compact import (
        N_MESSAGES_TO_KEEP,
        MIN_CONDENSE_THRESHOLD,
        MAX_CONDENSE_THRESHOLD,
    )
    
    print(f"TypeScript constants (直接来自 TypeScript 代码):")
    print(f"  N_MESSAGES_TO_KEEP = {N_MESSAGES_TO_KEEP}")
    print(f"  MIN_CONDENSE_THRESHOLD = {MIN_CONDENSE_THRESHOLD}")
    print(f"  MAX_CONDENSE_THRESHOLD = {MAX_CONDENSE_THRESHOLD}")
    print()
    
    # 使用这些常量
    memory = LLMCompactMessageHistoryGenerator(
        n_messages_to_keep=N_MESSAGES_TO_KEEP,
        min_messages_for_summary=MIN_CONDENSE_THRESHOLD,
    )
    
    print("✓ 使用 TypeScript 原始常量创建 memory")
    print()


def example_all_actions_equal():
    """展示所有动作一视同仁的处理"""
    print("=== 所有动作一视同仁 ===\n")
    
    memory = LLMCompactMessageHistoryGenerator()
    
    print("LLM Compact 的特点：")
    print("  ✓ ViewCode 和其他动作同等对待")
    print("  ✓ 不做特殊处理或优先级判断")
    print("  ✓ 所有消息都参与 LLM 摘要")
    print()
    
    print("与 compact.py 的对比：")
    print("  compact.py:")
    print("    - ViewCode: 特殊处理，总是保留")
    print("    - 其他动作: Token 计算，可能跳过")
    print()
    print("  llm_compact.py:")
    print("    - ViewCode: 正常处理")
    print("    - 其他动作: 正常处理")
    print("    - 所有动作: 都可能被 LLM 摘要")
    print()


def example_typescript_flow():
    """展示 TypeScript 的完整处理流程"""
    print("=== TypeScript 处理流程 ===\n")
    
    print("假设有 10 条消息的对话：")
    print()
    print("原始消息:")
    print("  1. [用户] 请修复 main.py 的 bug")
    print("  2. [助手] 我会帮你修复")
    print("  3. [动作] ViewCode(main.py)")
    print("  4. [观察] def main(): ...")
    print("  5. [动作] EditFile(main.py)")
    print("  6. [观察] 已编辑文件")
    print("  7. [动作] RunTests")
    print("  8. [观察] 2 passed, 1 failed")
    print("  9. [动作] ViewCode(test.py)")
    print("  10. [观察] def test_foo(): ...")
    print()
    
    print("TypeScript/LLM Compact 处理后:")
    print("  ┌─────────────────────────────────────┐")
    print("  │ 1. [用户] 请修复 main.py 的 bug     │ ← 首条消息（保留）")
    print("  └─────────────────────────────────────┘")
    print("  ┌─────────────────────────────────────┐")
    print("  │ 2. [助手] [SUMMARY]                 │ ← LLM 摘要（2-7 压缩）")
    print("  │    用户要求修复 main.py 的 bug。    │")
    print("  │    我查看了代码，进行了编辑，       │")
    print("  │    运行测试发现 1 个测试失败...     │")
    print("  └─────────────────────────────────────┘")
    print("  ┌─────────────────────────────────────┐")
    print("  │ 8. [观察] 2 passed, 1 failed        │ ← 最后 3 条（保留）")
    print("  │ 9. [动作] ViewCode(test.py)        │")
    print("  │ 10. [观察] def test_foo(): ...      │")
    print("  └─────────────────────────────────────┘")
    print()
    
    print("结构: [首条, LLM摘要, 最后N条]")
    print()


def example_cost_monitoring():
    """成本监控示例"""
    print("=== 成本监控 ===\n")
    
    completion_model = BaseCompletionModel(
        model="claude-3-5-sonnet-20241022",
        temperature=0.0,
    )
    
    memory = LLMCompactMessageHistoryGenerator()
    memory.set_completion_model(completion_model)
    
    # 在实际使用后
    # await agent.run(node)
    
    # 查看成本
    total_cost = memory.total_summary_cost
    print(f"LLM 摘要累计成本: ${total_cost:.4f}")
    print()
    
    print("注意：")
    print("  - 每次 LLM 摘要都会产生成本")
    print("  - 成本取决于消息数量和模型")
    print("  - TypeScript 同样会追踪成本")
    print()


def example_custom_summary_prompt():
    """自定义摘要提示词"""
    print("=== 自定义摘要提示词 ===\n")
    
    # TypeScript 使用的是固定的 SUMMARY_PROMPT
    # 但我们可以自定义
    
    custom_prompt = """
Create a brief summary of the conversation focusing on:
1. What files were viewed or edited
2. What tests were run
3. What the next step should be

Keep it under 200 words.
"""
    
    memory = LLMCompactMessageHistoryGenerator(
        summary_prompt=custom_prompt,  # 自定义提示词
    )
    
    print("✓ 使用自定义摘要提示词")
    print()
    print("TypeScript 默认提示词更详细（包括 6 个部分）")
    print("Python 可以根据需要自定义")
    print()


def example_comparison():
    """对比不同实现"""
    print("=== 实现对比 ===\n")
    
    print("┌────────────────┬──────────────┬──────────────┬──────────────┐")
    print("│ 特性           │ TypeScript   │ compact.py   │ llm_compact  │")
    print("├────────────────┼──────────────┼──────────────┼──────────────┤")
    print("│ 压缩策略       │ LLM 摘要     │ 规则压缩     │ LLM 摘要     │")
    print("│ ViewCode处理   │ 一视同仁     │ 特殊处理     │ 一视同仁     │")
    print("│ 成本           │ 有           │ 零           │ 有           │")
    print("│ 速度           │ 慢(2-5秒)    │ 快(<10ms)    │ 慢(2-5秒)    │")
    print("│ 结构           │ 固定         │ 灵活         │ 固定         │")
    print("│ Token管理      │ LLM自动      │ 手动计算     │ LLM自动      │")
    print("└────────────────┴──────────────┴──────────────┴──────────────┘")
    print()
    
    print("llm_compact.py 是 TypeScript 的忠实翻译")
    print("  - 相同的逻辑")
    print("  - 相同的常量")
    print("  - 相同的提示词")
    print("  - 相同的结构")
    print()


def example_when_to_use():
    """何时使用 LLM Compact"""
    print("=== 何时使用 LLM Compact ===\n")
    
    print("✓ 适用场景：")
    print("  1. 需要与 TypeScript 行为完全一致")
    print("  2. 从 TypeScript 迁移到 Python")
    print("  3. 信任 TypeScript 的设计")
    print("  4. 需要语义理解的摘要")
    print()
    
    print("✗ 不适用场景：")
    print("  1. 需要零成本压缩")
    print("     → 使用 CompactMessageHistoryGenerator")
    print()
    print("  2. 需要混合策略")
    print("     → 使用 SmartCompactMessageHistoryGenerator")
    print()
    print("  3. 需要特殊处理 ViewCode")
    print("     → 使用 CompactMessageHistoryGenerator")
    print()
    print("  4. 需要更快的速度")
    print("     → 使用规则压缩")
    print()


def example_fallback_behavior():
    """降级行为示例"""
    print("=== 降级行为 ===\n")
    
    # 未设置 completion model
    memory = LLMCompactMessageHistoryGenerator()
    
    print("如果未设置 completion model：")
    print("  ⚠️  会自动降级到父类实现")
    print("  ⚠️  使用 compact.py 的规则压缩")
    print()
    
    # 正确设置
    completion_model = BaseCompletionModel(model="claude-3-5-sonnet-20241022")
    memory.set_completion_model(completion_model)
    
    print("设置 completion model 后：")
    print("  ✓ 使用 LLM 摘要")
    print("  ✓ 遵循 TypeScript 逻辑")
    print()
    
    print("其他降级场景：")
    print("  - LLM 调用失败 → 返回原始消息")
    print("  - 摘要未减少 Token → 返回原始消息")
    print("  - 消息数不足 → 返回所有消息")
    print()


def main():
    """运行所有示例"""
    examples = [
        ("基础使用", example_basic_usage),
        ("TypeScript 常量", example_typescript_constants),
        ("所有动作一视同仁", example_all_actions_equal),
        ("TypeScript 处理流程", example_typescript_flow),
        ("成本监控", example_cost_monitoring),
        ("自定义摘要提示词", example_custom_summary_prompt),
        ("实现对比", example_comparison),
        ("何时使用", example_when_to_use),
        ("降级行为", example_fallback_behavior),
    ]
    
    print("=" * 70)
    print("LLMCompactMessageHistoryGenerator 使用示例")
    print("(严格按照 TypeScript 实现)")
    print("=" * 70)
    print()
    
    for title, example_func in examples:
        try:
            example_func()
        except Exception as e:
            print(f"❌ Error in {title}: {e}\n")
    
    print("=" * 70)
    print("示例运行完成")
    print("=" * 70)
    print()
    
    print("💡 提示：")
    print("  - LLM Compact 完全遵循 TypeScript 逻辑")
    print("  - 不做任何擅自优化或修改")
    print("  - 所有动作一视同仁")
    print("  - 必须设置 completion model")


if __name__ == "__main__":
    main()
