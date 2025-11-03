import logging
from typing import Optional

from pydantic import Field, PrivateAttr

from moatless.completion.base import BaseCompletionModel, CompletionResponse
from moatless.completion.schema import (
    AllMessageValues,
    ChatCompletionAssistantMessage,
    ChatCompletionTextObject,
    ChatCompletionUserMessage,
)
from moatless.message_history.compact import CompactMessageHistoryGenerator, NodeMessage
from moatless.node import Node
from moatless.utils.tokenizer import count_tokens
from moatless.workspace import Workspace

logger = logging.getLogger(__name__)

# Number of recent messages to always keep when summarizing
N_MESSAGES_TO_KEEP = 3

# Minimum percentage of context window to trigger LLM condensing
MIN_CONDENSE_THRESHOLD = 5

# Maximum percentage of context window to trigger LLM condensing
MAX_CONDENSE_THRESHOLD = 100

DEFAULT_SUMMARY_PROMPT = """\
Your task is to create a detailed summary of the conversation so far, paying close attention to the user's explicit requests and your previous actions.
This summary should be thorough in capturing technical details, code patterns, and architectural decisions that would be essential for continuing with the conversation and supporting any continuing tasks.

Your summary should be structured as follows:
Context: The context to continue the conversation with. If applicable based on the current task, this should include:
  1. Previous Conversation: High level details about what was discussed throughout the entire conversation with the user. This should be written to allow someone to be able to follow the general overarching conversation flow.
  2. Current Work: Describe in detail what was being worked on prior to this request to summarize the conversation. Pay special attention to the more recent messages in the conversation.
  3. Key Technical Concepts: List all important technical concepts, technologies, coding conventions, and frameworks discussed, which might be relevant for continuing with this work.
  4. Relevant Files and Code: If applicable, enumerate specific files and code sections examined, modified, or created for the task continuation. Pay special attention to the most recent messages and changes.
  5. Problem Solving: Document problems solved thus far and any ongoing troubleshooting efforts.
  6. Pending Tasks and Next Steps: Outline all pending tasks that you have explicitly been asked to work on, as well as list the next steps you will take for all outstanding work, if applicable. Include code snippets where they add clarity. For any next steps, include direct quotes from the most recent conversation showing exactly what task you were working on and where you left off. This should be verbatim to ensure there's no information loss in context between tasks.

Example summary structure:
1. Previous Conversation:
  [Detailed description]
2. Current Work:
  [Detailed description]
3. Key Technical Concepts:
  - [Concept 1]
  - [Concept 2]
  - [...]
4. Relevant Files and Code:
  - [File Name 1]
    - [Summary of why this file is important]
    - [Summary of the changes made to this file, if any]
    - [Important Code Snippet]
  - [File Name 2]
    - [Important Code Snippet]
  - [...]
5. Problem Solving:
  [Detailed description]
6. Pending Tasks and Next Steps:
  - [Task 1 details & next steps]
  - [Task 2 details & next steps]
  - [...]

Output only the summary of the conversation so far, without any additional commentary or explanation.
"""


class SmartCompactMessageHistoryGenerator(CompactMessageHistoryGenerator):
    """
    Smart hybrid message history generator that combines LLM summarization with rule-based compression.
    
    Strategy:
    1. First, use rule-based compression (from CompactMessageHistoryGenerator)
    2. If tokens still exceed threshold and LLM is available, use LLM summarization
    3. If LLM fails or is not available, fall back to rule-based compression
    
    This provides the best of both worlds:
    - Fast, cost-effective rule-based compression for most cases
    - Intelligent LLM summarization for complex long conversations
    - Graceful degradation if LLM fails
    """

    use_llm_summary: bool = Field(
        default=True,
        description="Whether to use LLM summarization when tokens exceed threshold",
    )
    
    llm_summary_threshold: Optional[int] = Field(
        default=None,
        description="Token threshold to trigger LLM summarization. If None, uses max_tokens * 0.7",
    )
    
    n_messages_to_keep: int = Field(
        default=N_MESSAGES_TO_KEEP,
        description="Number of recent message exchanges to preserve when using LLM summarization",
    )
    
    summary_prompt: str = Field(
        default=DEFAULT_SUMMARY_PROMPT,
        description="Custom prompt for LLM summarization",
    )
    
    min_messages_for_summary: int = Field(
        default=5,
        description="Minimum number of message exchanges required before attempting LLM summarization",
    )

    _completion_model: Optional[BaseCompletionModel] = PrivateAttr(default=None)
    _summary_cost: float = PrivateAttr(default=0.0)

    def set_completion_model(self, completion_model: BaseCompletionModel) -> None:
        """
        Set the completion model to use for LLM summarization.
        
        Args:
            completion_model: The completion model to use for generating summaries
        """
        self._completion_model = completion_model
        logger.info(f"Set completion model for smart compact: {completion_model.model}")

    @property
    def total_summary_cost(self) -> float:
        """Get the total cost of all summarization operations."""
        return self._summary_cost

    async def generate_messages(self, node: Node, workspace: Workspace) -> list[AllMessageValues]:
        """
        Generate messages with smart hybrid compression strategy.
        
        Strategy:
        1. Use rule-based compression from parent class
        2. If result still exceeds threshold and LLM is available, try LLM summarization
        3. Fall back to rule-based result if LLM fails
        
        Args:
            node: The node to generate messages for
            workspace: The workspace containing artifacts
            
        Returns:
            List of compressed messages
        """
        # First, try rule-based compression
        rule_based_messages = await super().generate_messages(node, workspace)
        rule_based_tokens = sum(count_tokens(self._message_to_string(msg)) for msg in rule_based_messages)
        
        logger.debug(f"Rule-based compression resulted in {len(rule_based_messages)} messages with {rule_based_tokens} tokens")
        
        # Determine if we should try LLM summarization
        should_use_llm = self._should_use_llm_summary(rule_based_tokens, node)
        
        if not should_use_llm:
            logger.debug("LLM summarization not needed or not available")
            return rule_based_messages
        
        # Try LLM summarization
        try:
            logger.info(f"Attempting LLM summarization (current tokens: {rule_based_tokens})")
            llm_messages = await self._llm_summarize_messages(node, workspace, rule_based_messages, rule_based_tokens)
            
            llm_tokens = sum(count_tokens(self._message_to_string(msg)) for msg in llm_messages)
            
            # Only use LLM result if it actually reduced tokens
            if llm_tokens < rule_based_tokens:
                logger.info(
                    f"LLM summarization successful: {len(llm_messages)} messages, "
                    f"{llm_tokens} tokens (reduced from {rule_based_tokens})"
                )
                return llm_messages
            else:
                logger.warning(
                    f"LLM summary did not reduce tokens ({llm_tokens} >= {rule_based_tokens}), "
                    f"using rule-based compression"
                )
                return rule_based_messages
                
        except Exception as e:
            logger.warning(f"LLM summarization failed: {e}, falling back to rule-based compression")
            return rule_based_messages

    def _should_use_llm_summary(self, current_tokens: int, node: Node) -> bool:
        """
        Determine if LLM summarization should be attempted.
        
        Args:
            current_tokens: Current token count after rule-based compression
            node: The node being processed
            
        Returns:
            True if LLM summarization should be attempted
        """
        # Check if LLM summarization is enabled
        if not self.use_llm_summary:
            return False
        
        # Check if completion model is available
        if not self._completion_model:
            logger.debug("No completion model available for LLM summarization")
            return False
        
        # Check if we have enough messages to warrant summarization
        trajectory = node.get_trajectory()
        if len(trajectory) < self.min_messages_for_summary:
            logger.debug(f"Not enough messages for LLM summary ({len(trajectory)} < {self.min_messages_for_summary})")
            return False
        
        # Check if tokens exceed threshold
        threshold = self.llm_summary_threshold
        if threshold is None and self.max_tokens:
            # Default to 70% of max_tokens
            threshold = int(self.max_tokens * 0.7)
        
        if threshold and current_tokens > threshold:
            logger.debug(f"Tokens ({current_tokens}) exceed LLM summary threshold ({threshold})")
            return True
        
        return False

    async def _llm_summarize_messages(
        self,
        node: Node,
        workspace: Workspace,
        rule_based_messages: list[AllMessageValues],
        prev_context_tokens: int,
    ) -> list[AllMessageValues]:
        """
        Use LLM to summarize conversation history.
        
        Args:
            node: The node to generate messages for
            workspace: The workspace containing artifacts
            rule_based_messages: Messages from rule-based compression
            prev_context_tokens: Token count before summarization
            
        Returns:
            List of messages with LLM summary
            
        Raises:
            Exception: If LLM summarization fails
        """
        if not self._completion_model:
            raise ValueError("No completion model available for summarization")
        
        # Get node messages for processing
        node_messages = await self.get_node_messages(node)
        
        if len(node_messages) <= self.n_messages_to_keep + 1:
            raise ValueError("Not enough messages to summarize")
        
        # Preserve first message (task description) and last N messages
        first_node_message = node_messages[0] if node_messages else None
        messages_to_summarize = self._get_messages_since_last_summary(node_messages[:-self.n_messages_to_keep])
        keep_messages = node_messages[-self.n_messages_to_keep:]
        
        # Check if there's already a recent summary
        if any(msg.assistant_message and "[SUMMARY]" in (msg.assistant_message or "") for msg in keep_messages):
            raise ValueError("Recent summary already exists in kept messages")
        
        if len(messages_to_summarize) <= 1:
            raise ValueError("Not enough messages to summarize after filtering")
        
        # Convert to LLM message format
        llm_messages = self._node_messages_to_llm_format(messages_to_summarize)
        
        # Add final request for summary
        llm_messages.append(
            ChatCompletionUserMessage(
                role="user",
                content="Summarize the conversation so far, as described in the prompt instructions.",
                cache_control=None,
            )
        )
        
        # Create a temporary completion model for summarization
        # We don't want to interfere with the main model's state
        summary_model = self._completion_model
        
        # Call LLM for summary (without using response schema)
        logger.debug(f"Calling LLM with {len(llm_messages)} messages for summarization")
        
        # Use direct litellm call for simpler summary generation
        import litellm
        response = await litellm.acompletion(
            model=summary_model.model,
            messages=[
                {"role": "system", "content": self.summary_prompt},
                *[self._convert_message_for_litellm(msg) for msg in llm_messages],
            ],
            temperature=0.0,
            max_tokens=2000,
            api_base=summary_model.model_base_url,
            api_key=summary_model.model_api_key,
        )
        
        summary_text = response.choices[0].message.content.strip()
        
        if not summary_text:
            raise ValueError("LLM returned empty summary")
        
        # Track cost
        usage = response.usage
        if usage:
            input_cost = (usage.prompt_tokens / 1_000_000) * 3.0  # Rough estimate
            output_cost = (usage.completion_tokens / 1_000_000) * 15.0
            cost = input_cost + output_cost
            self._summary_cost += cost
            logger.info(f"LLM summary cost: ${cost:.4f} (cumulative: ${self._summary_cost:.4f})")
        
        # Create summary message
        summary_node_message = NodeMessage(
            assistant_message=f"[SUMMARY]\n\n{summary_text}",
        )
        
        # Reconstruct node messages: [first, summary, keep_messages]
        result_node_messages = []
        if first_node_message:
            result_node_messages.append(first_node_message)
        result_node_messages.append(summary_node_message)
        result_node_messages.extend(keep_messages)
        
        # Convert back to API message format
        return self._node_messages_to_api_format(result_node_messages)

    def _get_messages_since_last_summary(self, node_messages: list[NodeMessage]) -> list[NodeMessage]:
        """
        Get messages since the last summary, including the summary.
        
        Args:
            node_messages: List of node messages
            
        Returns:
            Messages since last summary, or all messages if no summary exists
        """
        # Find the last summary message
        last_summary_idx = -1
        for i in range(len(node_messages) - 1, -1, -1):
            msg = node_messages[i]
            if msg.assistant_message and "[SUMMARY]" in (msg.assistant_message or ""):
                last_summary_idx = i
                break
        
        if last_summary_idx == -1:
            return node_messages
        
        messages_since_summary = node_messages[last_summary_idx:]
        
        # Ensure first message is included for context
        if last_summary_idx > 0:
            first_message = node_messages[0]
            if first_message not in messages_since_summary:
                return [first_message] + messages_since_summary
        
        return messages_since_summary

    def _node_messages_to_llm_format(self, node_messages: list[NodeMessage]) -> list[AllMessageValues]:
        """
        Convert NodeMessage objects to LLM message format for summarization.
        
        Args:
            node_messages: List of NodeMessage objects
            
        Returns:
            List of messages in LLM format
        """
        messages = []
        
        for node_msg in node_messages:
            # Add user message if present
            if node_msg.user_message:
                messages.append(
                    ChatCompletionUserMessage(
                        role="user",
                        content=node_msg.user_message,
                        cache_control=None,
                    )
                )
            
            # Add assistant message if present
            if node_msg.assistant_message:
                messages.append(
                    ChatCompletionAssistantMessage(
                        role="assistant",
                        content=node_msg.assistant_message,
                    )
                )
            
            # Convert actions and observations to simple text format
            if node_msg.actions and node_msg.observations:
                action_text = ""
                for action, observation in zip(node_msg.actions, node_msg.observations, strict=True):
                    action_text += f"\nAction: {action.name}\n"
                    action_text += f"{action.to_prompt()}\n"
                    action_text += f"Observation: {observation}\n"
                
                if action_text:
                    messages.append(
                        ChatCompletionAssistantMessage(
                            role="assistant",
                            content=action_text.strip(),
                        )
                    )
        
        return messages

    def _node_messages_to_api_format(self, node_messages: list[NodeMessage]) -> list[AllMessageValues]:
        """
        Convert NodeMessage objects to API message format.
        
        This uses the parent class's format for consistency.
        
        Args:
            node_messages: List of NodeMessage objects
            
        Returns:
            List of messages in API format
        """
        messages = []
        
        for node_msg in node_messages:
            # Add user message
            if node_msg.user_message:
                messages.append(
                    ChatCompletionUserMessage(
                        role="user",
                        content=node_msg.user_message,
                        cache_control=None,
                    )
                )
            
            # Add assistant message (including summaries)
            if node_msg.assistant_message:
                messages.append(
                    ChatCompletionAssistantMessage(
                        role="assistant",
                        content=node_msg.assistant_message,
                    )
                )
            
            # Add actions and observations in compact format
            if node_msg.actions and node_msg.observations:
                tool_calls = []
                tool_idx = len([m for m in messages if isinstance(m, dict) and m.get("role") == "assistant"])
                
                for i, (action, observation) in enumerate(zip(node_msg.actions, node_msg.observations, strict=True)):
                    tool_idx += 1
                    tool_call_id = f"tool_{tool_idx}"
                    
                    exclude = None
                    if not self.thoughts_in_action:
                        exclude = {"thoughts"}
                    
                    tool_calls.append({
                        "id": tool_call_id,
                        "type": "function",
                        "function": {
                            "name": action.name,
                            "arguments": action.model_dump_json(exclude=exclude),
                        },
                    })
                
                # Add assistant message with tool calls
                if tool_calls:
                    messages.append({
                        "role": "assistant",
                        "tool_calls": tool_calls,
                    })
                
                # Add tool responses
                for i, observation in enumerate(node_msg.observations):
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_calls[i]["id"],
                        "content": observation,
                    })
        
        return messages

    def _convert_message_for_litellm(self, message: AllMessageValues) -> dict:
        """Convert message to litellm format."""
        if isinstance(message, dict):
            return message
        return {
            "role": message["role"],
            "content": self._extract_content(message.get("content")),
        }

    def _extract_content(self, content) -> str:
        """Extract string content from various content formats."""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
                elif isinstance(item, ChatCompletionTextObject):
                    text_parts.append(item.get("text", ""))
            return "\n".join(text_parts)
        return str(content)

    def _message_to_string(self, message: AllMessageValues) -> str:
        """Convert message to string for token counting."""
        if isinstance(message, dict):
            content = message.get("content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return self._extract_content(content)
            return str(message)
        return str(message)
