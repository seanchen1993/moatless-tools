"""
示例：如何使用 SmartCompactMessageHistoryGenerator

这个示例展示了如何在 Agent 中使用智能混合压缩策略。
"""

from moatless.agent import ActionAgent
from moatless.completion import BaseCompletionModel
from moatless.message_history.smart_compact import SmartCompactMessageHistoryGenerator
from moatless.actions import (
    ViewCode,
    EditFile,
    SemanticSearch,
    Finish,
)


def create_agent_with_smart_compact():
    """创建一个使用智能混合压缩的 Agent"""
    
    # 1. 创建 completion model
    completion_model = BaseCompletionModel(
        model="claude-3-5-sonnet-20241022",
        temperature=0.0,
        max_tokens=4000,
    )
    
    # 2. 创建 SmartCompactMessageHistoryGenerator
    memory = SmartCompactMessageHistoryGenerator(
        # 基础配置（继承自 CompactMessageHistoryGenerator）
        max_tokens=100000,  # 总 Token 限制
        max_tokens_per_observation=10000,  # 每个观察的 Token 限制
        include_file_context=True,  # 包含文件上下文
        include_git_patch=True,  # 包含 Git diff
        thoughts_in_action=False,  # 思考内容放在消息中
        message_cache=False,  # 是否启用消息缓存
        
        # SmartCompact 特有配置
        use_llm_summary=True,  # 启用 LLM 摘要
        llm_summary_threshold=70000,  # 超过 70000 token 触发 LLM 摘要
        n_messages_to_keep=3,  # LLM 摘要时保留最近的 3 条消息
        min_messages_for_summary=5,  # 至少 5 条消息才尝试摘要
        summary_prompt=None,  # 使用默认摘要提示词（也可以自定义）
    )
    
    # 3. 设置 completion model（用于 LLM 摘要）
    memory.set_completion_model(completion_model)
    
    # 4. 创建 Agent
    agent = ActionAgent(
        agent_id="smart-compact-agent",
        completion_model=completion_model,
        system_prompt="""You are a helpful coding assistant.
Your task is to help users with their coding tasks by:
1. Viewing code files
2. Searching for relevant code
3. Making necessary edits
4. Finishing when the task is complete
""",
        actions=[
            ViewCode(),
            SemanticSearch(),
            EditFile(),
            Finish(),
        ],
        memory=memory,  # 使用智能混合压缩
    )
    
    return agent, memory


def example_basic_usage():
    """基础使用示例"""
    print("=== 基础使用示例 ===\n")
    
    agent, memory = create_agent_with_smart_compact()
    
    print(f"Agent ID: {agent.agent_id}")
    print(f"Memory type: {type(memory).__name__}")
    print(f"LLM summary enabled: {memory.use_llm_summary}")
    print(f"LLM summary threshold: {memory.llm_summary_threshold} tokens")
    print(f"Messages to keep: {memory.n_messages_to_keep}")
    print()


def example_cost_monitoring():
    """成本监控示例"""
    print("=== 成本监控示例 ===\n")
    
    agent, memory = create_agent_with_smart_compact()
    
    # 在运行任务后，检查摘要成本
    # async with agent.run_simple("Fix the bug in main.py"):
    #     pass
    
    # 获取累计成本
    total_cost = memory.total_summary_cost
    print(f"Total LLM summarization cost: ${total_cost:.4f}")
    
    # 根据成本决定是否继续使用 LLM 摘要
    if total_cost > 0.50:
        print("⚠️  Cost limit reached, disabling LLM summarization")
        memory.use_llm_summary = False
    else:
        print("✓ Cost within limit, LLM summarization remains enabled")
    print()


def example_custom_summary_prompt():
    """自定义摘要提示词示例"""
    print("=== 自定义摘要提示词示例 ===\n")
    
    custom_prompt = """
Create a concise technical summary focusing on:
1. Files viewed and their purpose
2. Code changes made (with file paths)
3. Test results and their status
4. Next steps to complete the task

Keep the summary under 500 words and use bullet points for clarity.
Output only the summary without any preamble or conclusion.
"""
    
    memory = SmartCompactMessageHistoryGenerator(
        max_tokens=100000,
        use_llm_summary=True,
        llm_summary_threshold=60000,
        summary_prompt=custom_prompt,  # 使用自定义提示词
    )
    
    print("Using custom summary prompt:")
    print(custom_prompt[:200] + "...")
    print()


def example_dynamic_threshold():
    """动态调整阈值示例"""
    print("=== 动态调整阈值示例 ===\n")
    
    agent, memory = create_agent_with_smart_compact()
    
    # 模拟根据任务复杂度调整
    task_complexity = "high"  # 可以是 'low', 'medium', 'high'
    
    if task_complexity == "high":
        # 复杂任务：提供更多上下文，较少使用 LLM 摘要
        memory.llm_summary_threshold = 90000
        memory.n_messages_to_keep = 5
        print("✓ High complexity: threshold=90000, keep=5")
    elif task_complexity == "medium":
        # 中等任务：平衡设置
        memory.llm_summary_threshold = 70000
        memory.n_messages_to_keep = 3
        print("✓ Medium complexity: threshold=70000, keep=3")
    else:
        # 简单任务：更积极地使用 LLM 摘要
        memory.llm_summary_threshold = 50000
        memory.n_messages_to_keep = 2
        print("✓ Low complexity: threshold=50000, keep=2")
    print()


def example_disable_llm_summary():
    """禁用 LLM 摘要，只使用规则压缩"""
    print("=== 禁用 LLM 摘要示例 ===\n")
    
    # 创建只使用规则压缩的版本（零成本）
    memory = SmartCompactMessageHistoryGenerator(
        max_tokens=100000,
        max_tokens_per_observation=10000,
        use_llm_summary=False,  # 禁用 LLM 摘要
    )
    
    print("LLM summary disabled - using only rule-based compression")
    print("Cost: $0.00 (no LLM calls)")
    print("Speed: <10ms per compression")
    print()


def example_comparison():
    """对比不同策略"""
    print("=== 策略对比 ===\n")
    
    strategies = {
        "Rule-based only": SmartCompactMessageHistoryGenerator(
            max_tokens=100000,
            use_llm_summary=False,
        ),
        "Smart hybrid (conservative)": SmartCompactMessageHistoryGenerator(
            max_tokens=100000,
            use_llm_summary=True,
            llm_summary_threshold=90000,  # 高阈值，少用 LLM
        ),
        "Smart hybrid (aggressive)": SmartCompactMessageHistoryGenerator(
            max_tokens=100000,
            use_llm_summary=True,
            llm_summary_threshold=50000,  # 低阈值，多用 LLM
        ),
    }
    
    for name, strategy in strategies.items():
        print(f"{name}:")
        print(f"  - LLM enabled: {strategy.use_llm_summary}")
        if strategy.use_llm_summary:
            print(f"  - Threshold: {strategy.llm_summary_threshold} tokens")
        print(f"  - Messages to keep: {strategy.n_messages_to_keep}")
        print()


def example_best_practices():
    """最佳实践示例"""
    print("=== 最佳实践 ===\n")
    
    # 1. 总是设置 completion model
    completion_model = BaseCompletionModel(
        model="claude-3-5-sonnet-20241022",
        temperature=0.0,
        max_tokens=4000,
    )
    
    # 2. 根据使用场景选择合适的配置
    memory = SmartCompactMessageHistoryGenerator(
        max_tokens=100000,
        max_tokens_per_observation=10000,
        
        # 对于代码编辑任务，使用较高的阈值
        use_llm_summary=True,
        llm_summary_threshold=80000,  # 80% of max_tokens
        
        # 保留足够的最近消息以维持上下文连贯性
        n_messages_to_keep=4,
        
        # 确保有足够的历史再进行摘要
        min_messages_for_summary=6,
    )
    
    # 3. 设置 completion model
    memory.set_completion_model(completion_model)
    
    print("✓ Best practices applied:")
    print("  - Completion model set")
    print("  - Threshold at 80% of max_tokens")
    print("  - Keeping 4 recent messages")
    print("  - Minimum 6 messages for summary")
    print()
    
    # 4. 监控成本
    print("Remember to monitor cost:")
    print("  cost = memory.total_summary_cost")
    print()


def main():
    """运行所有示例"""
    examples = [
        ("基础使用", example_basic_usage),
        ("成本监控", example_cost_monitoring),
        ("自定义摘要提示词", example_custom_summary_prompt),
        ("动态调整阈值", example_dynamic_threshold),
        ("禁用 LLM 摘要", example_disable_llm_summary),
        ("策略对比", example_comparison),
        ("最佳实践", example_best_practices),
    ]
    
    print("=" * 60)
    print("SmartCompactMessageHistoryGenerator 使用示例")
    print("=" * 60)
    print()
    
    for title, example_func in examples:
        try:
            example_func()
        except Exception as e:
            print(f"❌ Error in {title}: {e}\n")
    
    print("=" * 60)
    print("示例运行完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
