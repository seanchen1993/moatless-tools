"""
LLM-based Compact Message History Generator

This implementation strictly follows the TypeScript approach for intelligent compression:
1. Always preserve the first message (task description)
2. Always preserve the last N messages (recent context)
3. Summarize the middle messages using LLM
4. Final structure: [first_message, summary, last_N_messages]

This is a direct translation of the TypeScript summarizeConversation logic.
"""

import logging
from typing import List, Optional

from pydantic import Field, PrivateAttr

from moatless.completion.base import BaseCompletionModel
from moatless.completion.schema import (
    AllMessageValues,
    ChatCompletionAssistantMessage,
    ChatCompletionTextObject,
    ChatCompletionToolMessage,
    ChatCompletionUserMessage,
)
from moatless.message_history.compact import CompactMessageHistoryGenerator, NodeMessage
from moatless.node import Node
from moatless.utils.tokenizer import count_tokens
from moatless.workspace import Workspace

logger = logging.getLogger(__name__)

# Constants from TypeScript implementation
N_MESSAGES_TO_KEEP = 3
MIN_CONDENSE_THRESHOLD = 5
MAX_CONDENSE_THRESHOLD = 100

# Summary prompt from TypeScript implementation (exactly as in TypeScript)
SUMMARY_PROMPT = """\
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


class LLMCompactMessageHistoryGenerator(CompactMessageHistoryGenerator):
    """
    LLM-based Compact Message History Generator
    
    This implementation strictly follows the TypeScript approach:
    - Always preserve first message
    - Always preserve last N messages  
    - Use LLM to summarize middle messages
    - No distinction between ViewCode and other actions
    - All actions treated equally
    
    This is the TypeScript logic translated to Python.
    """

    n_messages_to_keep: int = Field(
        default=N_MESSAGES_TO_KEEP,
        description="Number of recent message exchanges to preserve (from TypeScript N_MESSAGES_TO_KEEP)",
    )
    
    min_messages_for_summary: int = Field(
        default=MIN_CONDENSE_THRESHOLD,
        description="Minimum number of messages required before attempting summarization",
    )
    
    summary_prompt: str = Field(
        default=SUMMARY_PROMPT,
        description="Prompt for LLM summarization (from TypeScript SUMMARY_PROMPT)",
    )
    
    _completion_model: Optional[BaseCompletionModel] = PrivateAttr(default=None)
    _total_summary_cost: float = PrivateAttr(default=0.0)

    def set_completion_model(self, completion_model: BaseCompletionModel) -> None:
        """
        Set the completion model to use for LLM summarization.
        
        Args:
            completion_model: The completion model for generating summaries
        """
        self._completion_model = completion_model
        logger.info(f"Set completion model for LLM compact: {completion_model.model}")

    @property
    def total_summary_cost(self) -> float:
        """Get the total cost of all summarization operations."""
        return self._total_summary_cost

    async def generate_messages(self, node: Node, workspace: Workspace) -> list[AllMessageValues]:
        """
        Generate messages following the TypeScript approach.
        
        TypeScript logic:
        1. Get all node messages
        2. Preserve first message
        3. Preserve last N messages
        4. Summarize middle messages with LLM
        5. Return: [first, summary, last_N]
        
        Args:
            node: The node to generate messages for
            workspace: The workspace containing artifacts
            
        Returns:
            List of messages following TypeScript structure
        """
        if not self._completion_model:
            logger.warning("No completion model set, falling back to parent implementation")
            return await super().generate_messages(node, workspace)
        
        # Get node messages (using parent's logic to collect messages)
        # But we treat all actions equally (no ViewCode special handling)
        node_messages = await self._get_all_node_messages_equally(node)
        
        logger.debug(f"Collected {len(node_messages)} node messages")
        
        # Check if we have enough messages to warrant summarization
        # TypeScript: if (messagesToSummarize.length <= 1) return error
        if len(node_messages) <= self.n_messages_to_keep + 1:
            logger.debug(
                f"Not enough messages to summarize ({len(node_messages)} <= {self.n_messages_to_keep + 1}), "
                "returning all messages"
            )
            return await self._convert_node_messages_to_api_format(node_messages)
        
        # TypeScript logic: Always preserve the first message
        first_message = node_messages[0] if node_messages else None
        
        # TypeScript logic: Get messages to summarize (exclude last N)
        messages_to_summarize = self._get_messages_since_last_summary(
            node_messages[:-self.n_messages_to_keep]
        )
        
        # TypeScript logic: Keep last N messages
        keep_messages = node_messages[-self.n_messages_to_keep:]
        
        # Check if there's a recent summary in kept messages
        # TypeScript: const recentSummaryExists = keepMessages.some(message => message.isSummary)
        recent_summary_exists = any(
            msg.assistant_message and "[SUMMARY]" in (msg.assistant_message or "")
            for msg in keep_messages
        )
        
        if recent_summary_exists:
            logger.debug("Recent summary exists in kept messages, skipping summarization")
            return await self._convert_node_messages_to_api_format(node_messages)
        
        # Check minimum messages requirement
        if len(messages_to_summarize) <= 1:
            logger.debug("Not enough messages to summarize after filtering")
            return await self._convert_node_messages_to_api_format(node_messages)
        
        # Calculate current context tokens
        prev_context_tokens = sum(
            count_tokens(self._node_message_to_string(msg)) 
            for msg in node_messages
        )
        
        # Call LLM to generate summary (TypeScript approach)
        try:
            summary_text, cost = await self._call_llm_for_summary(messages_to_summarize)
            self._total_summary_cost += cost
            
            # Create summary message (TypeScript: summaryMessage)
            summary_message = NodeMessage(
                assistant_message=f"[SUMMARY]\n\n{summary_text}",
            )
            
            # Reconstruct messages following TypeScript structure:
            # [first message, summary, last N messages]
            new_node_messages = []
            if first_message:
                new_node_messages.append(first_message)
            new_node_messages.append(summary_message)
            new_node_messages.extend(keep_messages)
            
            # Calculate new context tokens
            new_context_tokens = sum(
                count_tokens(self._node_message_to_string(msg))
                for msg in new_node_messages
            )
            
            # TypeScript check: if (newContextTokens >= prevContextTokens) return error
            if new_context_tokens >= prev_context_tokens:
                logger.warning(
                    f"Summary did not reduce tokens ({new_context_tokens} >= {prev_context_tokens}), "
                    "using original messages"
                )
                return await self._convert_node_messages_to_api_format(node_messages)
            
            logger.info(
                f"LLM summarization successful: {len(new_node_messages)} messages, "
                f"{new_context_tokens} tokens (reduced from {prev_context_tokens}), "
                f"cost: ${cost:.4f}"
            )
            
            return await self._convert_node_messages_to_api_format(new_node_messages)
            
        except Exception as e:
            logger.error(f"LLM summarization failed: {e}, using original messages")
            return await self._convert_node_messages_to_api_format(node_messages)

    async def _get_all_node_messages_equally(self, node: Node) -> List[NodeMessage]:
        """
        Collect all node messages treating all actions equally.
        
        This is different from compact.py which treats ViewCode specially.
        Here we follow TypeScript: all messages are treated the same way.
        
        Args:
            node: The node to process
            
        Returns:
            List of NodeMessage objects
        """
        previous_nodes = node.get_trajectory()
        logger.debug(f"Processing {len(previous_nodes)} previous nodes")
        
        if not previous_nodes:
            return []
        
        node_messages = []
        
        # Process nodes in reverse order (newest first) like compact.py
        # But treat all actions equally - no special ViewCode handling
        for previous_node in reversed(previous_nodes):
            current_messages: List[NodeMessage] = []
            
            # User and assistant messages
            user_message = previous_node.user_message
            assistant_message = previous_node.assistant_message
            
            if previous_node.feedback_data and not user_message:
                user_message = previous_node.feedback_data.feedback
            
            if user_message or assistant_message:
                current_messages.append(
                    NodeMessage(
                        user_message=user_message,
                        assistant_message=assistant_message,
                    )
                )
            
            # Process action steps - ALL ACTIONS TREATED EQUALLY
            if previous_node.action_steps:
                actions = []
                observations = []
                
                for action_step in previous_node.action_steps:
                    if not action_step.observation:
                        continue
                    
                    # No distinction between ViewCode and others
                    # Just collect all actions and observations
                    actions.append(action_step.action)
                    
                    # Use full message (not summary)
                    observation_str = action_step.observation.message or "No output found."
                    observations.append(observation_str)
                
                if actions and observations:
                    current_messages.append(
                        NodeMessage(
                            actions=actions,
                            observations=observations,
                        )
                    )
            
            # Add to node_messages (reversed, so prepend)
            node_messages = current_messages + node_messages
        
        logger.debug(f"Collected {len(node_messages)} node messages (all actions treated equally)")
        return node_messages

    def _get_messages_since_last_summary(self, node_messages: List[NodeMessage]) -> List[NodeMessage]:
        """
        Get messages since the last summary.
        
        TypeScript: getMessagesSinceLastSummary()
        Returns all messages if there's no summary.
        
        Args:
            node_messages: List of node messages
            
        Returns:
            Messages since last summary, or all messages if no summary exists
        """
        # Find last summary in reverse
        last_summary_idx = -1
        for i in range(len(node_messages) - 1, -1, -1):
            msg = node_messages[i]
            if msg.assistant_message and "[SUMMARY]" in (msg.assistant_message or ""):
                last_summary_idx = i
                break
        
        if last_summary_idx == -1:
            # No summary found, return all messages
            return node_messages
        
        # Return messages since summary (including the summary)
        messages_since_summary = node_messages[last_summary_idx:]
        
        # TypeScript: Bedrock requires first message to be user message
        # Preserve original first message to maintain context
        if messages_since_summary and messages_since_summary[0].user_message is None:
            original_first = node_messages[0]
            if original_first and original_first.user_message:
                return [original_first] + messages_since_summary
        
        return messages_since_summary

    async def _call_llm_for_summary(
        self, 
        messages_to_summarize: List[NodeMessage]
    ) -> tuple[str, float]:
        """
        Call LLM to generate summary.
        
        This follows the TypeScript approach exactly:
        1. Convert messages to LLM format
        2. Add final request message
        3. Call LLM with SUMMARY_PROMPT
        4. Return summary text and cost
        
        Args:
            messages_to_summarize: Messages to summarize
            
        Returns:
            Tuple of (summary_text, cost)
        """
        # Convert NodeMessages to API format for LLM
        llm_messages = self._convert_node_messages_to_llm_format(messages_to_summarize)
        
        # TypeScript: Add final request message
        llm_messages.append(
            ChatCompletionUserMessage(
                role="user",
                content="Summarize the conversation so far, as described in the prompt instructions.",
                cache_control=None,
            )
        )
        
        logger.debug(f"Calling LLM with {len(llm_messages)} messages for summarization")
        
        # Call LLM using litellm (TypeScript uses handlerToUse.createMessage)
        import litellm
        
        response = await litellm.acompletion(
            model=self._completion_model.model,
            messages=[
                {"role": "system", "content": self.summary_prompt},
                *[self._convert_message_to_dict(msg) for msg in llm_messages],
            ],
            temperature=0.0,
            max_tokens=2000,
            api_base=self._completion_model.model_base_url,
            api_key=self._completion_model.model_api_key,
        )
        
        summary_text = response.choices[0].message.content.strip()
        
        if not summary_text:
            raise ValueError("LLM returned empty summary")
        
        # Calculate cost (TypeScript tracks this)
        usage = response.usage
        cost = 0.0
        if usage:
            # Rough cost estimation (adjust based on your model)
            input_cost = (usage.prompt_tokens / 1_000_000) * 3.0
            output_cost = (usage.completion_tokens / 1_000_000) * 15.0
            cost = input_cost + output_cost
        
        logger.debug(f"LLM summary generated: {len(summary_text)} chars, cost: ${cost:.4f}")
        
        return summary_text, cost

    def _convert_node_messages_to_llm_format(
        self, 
        node_messages: List[NodeMessage]
    ) -> List[AllMessageValues]:
        """
        Convert NodeMessages to LLM message format.
        
        TypeScript: requestMessages = maybeRemoveImageBlocks([...messagesToSummarize, finalRequestMessage])
        
        Args:
            node_messages: List of NodeMessage objects
            
        Returns:
            List of messages in LLM format
        """
        messages = []
        
        for node_msg in node_messages:
            # User message
            if node_msg.user_message:
                messages.append(
                    ChatCompletionUserMessage(
                        role="user",
                        content=node_msg.user_message,
                        cache_control=None,
                    )
                )
            
            # Assistant message
            if node_msg.assistant_message:
                messages.append(
                    ChatCompletionAssistantMessage(
                        role="assistant",
                        content=node_msg.assistant_message,
                    )
                )
            
            # Actions and observations as simple text
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

    async def _convert_node_messages_to_api_format(
        self, 
        node_messages: List[NodeMessage]
    ) -> List[AllMessageValues]:
        """
        Convert NodeMessages to API message format.
        
        This uses the compact format from parent class.
        
        Args:
            node_messages: List of NodeMessage objects
            
        Returns:
            List of messages in API format
        """
        messages = []
        tool_idx = 0
        
        for node_msg in node_messages:
            # User message
            if node_msg.user_message:
                messages.append(
                    ChatCompletionUserMessage(
                        role="user",
                        content=node_msg.user_message,
                        cache_control=None,
                    )
                )
            
            # Assistant message (including summaries)
            if node_msg.assistant_message:
                messages.append(
                    ChatCompletionAssistantMessage(
                        role="assistant",
                        content=node_msg.assistant_message,
                    )
                )
            
            # Actions and observations in tool call format
            if node_msg.actions and node_msg.observations:
                tool_calls = []
                tool_responses = []
                
                for action, observation in zip(node_msg.actions, node_msg.observations, strict=True):
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
                    
                    tool_responses.append({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": observation,
                    })
                
                # Add assistant message with tool calls
                messages.append({
                    "role": "assistant",
                    "tool_calls": tool_calls,
                })
                
                # Add tool responses
                messages.extend(tool_responses)
        
        return messages

    def _convert_message_to_dict(self, message: AllMessageValues) -> dict:
        """Convert message to dict for litellm."""
        if isinstance(message, dict):
            return message
        
        content = message.get("content")
        if isinstance(content, list):
            # Extract text from content list
            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
            content = "\n".join(text_parts)
        
        return {
            "role": message["role"],
            "content": content or "",
        }

    def _node_message_to_string(self, node_msg: NodeMessage) -> str:
        """Convert NodeMessage to string for token counting."""
        parts = []
        
        if node_msg.user_message:
            parts.append(node_msg.user_message)
        
        if node_msg.assistant_message:
            parts.append(node_msg.assistant_message)
        
        if node_msg.actions and node_msg.observations:
            for action, obs in zip(node_msg.actions, node_msg.observations, strict=True):
                parts.append(action.model_dump_json())
                parts.append(obs)
        
        return "\n".join(parts)
