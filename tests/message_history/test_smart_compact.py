import pytest
from unittest.mock import Mock, AsyncMock, patch
from moatless.message_history.smart_compact import SmartCompactMessageHistoryGenerator
from moatless.node import Node
from moatless.workspace import Workspace
from moatless.completion.base import BaseCompletionModel


class TestSmartCompactMessageHistoryGenerator:
    """Test suite for SmartCompactMessageHistoryGenerator"""

    @pytest.fixture
    def mock_completion_model(self):
        """Create a mock completion model"""
        model = Mock(spec=BaseCompletionModel)
        model.model = "claude-3-5-sonnet-20241022"
        model.model_base_url = None
        model.model_api_key = None
        return model

    @pytest.fixture
    def generator(self, mock_completion_model):
        """Create a generator with default settings"""
        gen = SmartCompactMessageHistoryGenerator(
            max_tokens=100000,
            max_tokens_per_observation=10000,
            use_llm_summary=True,
            llm_summary_threshold=70000,
            n_messages_to_keep=3,
            min_messages_for_summary=5,
        )
        gen.set_completion_model(mock_completion_model)
        return gen

    @pytest.fixture
    def simple_node(self):
        """Create a simple node with few messages"""
        root = Node.create("Initial task")
        child = root.create_child()
        child.user_message = "Do something"
        child.assistant_message = "I will do it"
        return child

    @pytest.fixture
    def workspace(self):
        """Create a mock workspace"""
        return Mock(spec=Workspace)

    def test_initialization(self, generator):
        """Test that generator initializes correctly"""
        assert generator.use_llm_summary is True
        assert generator.llm_summary_threshold == 70000
        assert generator.n_messages_to_keep == 3
        assert generator.min_messages_for_summary == 5
        assert generator._completion_model is not None

    def test_set_completion_model(self, mock_completion_model):
        """Test setting completion model"""
        gen = SmartCompactMessageHistoryGenerator()
        assert gen._completion_model is None
        
        gen.set_completion_model(mock_completion_model)
        assert gen._completion_model == mock_completion_model

    def test_total_summary_cost_initial(self, generator):
        """Test that initial summary cost is zero"""
        assert generator.total_summary_cost == 0.0

    @pytest.mark.asyncio
    async def test_should_not_use_llm_when_disabled(self, generator, simple_node):
        """Test that LLM is not used when disabled"""
        generator.use_llm_summary = False
        result = generator._should_use_llm_summary(80000, simple_node)
        assert result is False

    @pytest.mark.asyncio
    async def test_should_not_use_llm_without_model(self, simple_node):
        """Test that LLM is not used when model is not set"""
        gen = SmartCompactMessageHistoryGenerator(
            use_llm_summary=True,
            llm_summary_threshold=70000,
        )
        result = gen._should_use_llm_summary(80000, simple_node)
        assert result is False

    @pytest.mark.asyncio
    async def test_should_not_use_llm_for_few_messages(self, generator, simple_node):
        """Test that LLM is not used when there are too few messages"""
        # simple_node only has 1 message in trajectory
        result = generator._should_use_llm_summary(80000, simple_node)
        assert result is False

    @pytest.mark.asyncio
    async def test_should_not_use_llm_below_threshold(self, generator):
        """Test that LLM is not used when tokens are below threshold"""
        # Create a node with enough messages
        root = Node.create("Initial task")
        for i in range(10):
            child = root.create_child()
            child.user_message = f"Message {i}"
            child.assistant_message = f"Response {i}"
            root = child
        
        # Below threshold
        result = generator._should_use_llm_summary(60000, root)
        assert result is False

    @pytest.mark.asyncio
    async def test_should_use_llm_when_conditions_met(self, generator):
        """Test that LLM is used when all conditions are met"""
        # Create a node with enough messages
        root = Node.create("Initial task")
        for i in range(10):
            child = root.create_child()
            child.user_message = f"Message {i}"
            child.assistant_message = f"Response {i}"
            root = child
        
        # Above threshold
        result = generator._should_use_llm_summary(80000, root)
        assert result is True

    @pytest.mark.asyncio
    async def test_fallback_to_rule_based_when_llm_disabled(self, generator, simple_node, workspace):
        """Test that it falls back to rule-based compression when LLM is disabled"""
        generator.use_llm_summary = False
        
        # Should use parent class's generate_messages
        messages = await generator.generate_messages(simple_node, workspace)
        
        # Should return some messages (exact format depends on parent implementation)
        assert isinstance(messages, list)

    @pytest.mark.asyncio
    async def test_extract_content_from_string(self, generator):
        """Test extracting content from string"""
        result = generator._extract_content("Hello world")
        assert result == "Hello world"

    @pytest.mark.asyncio
    async def test_extract_content_from_list(self, generator):
        """Test extracting content from list of text objects"""
        content = [
            {"type": "text", "text": "Hello"},
            {"type": "text", "text": "world"},
        ]
        result = generator._extract_content(content)
        assert "Hello" in result
        assert "world" in result

    @pytest.mark.asyncio
    async def test_message_to_string_with_dict(self, generator):
        """Test converting dict message to string"""
        message = {"role": "user", "content": "Test message"}
        result = generator._message_to_string(message)
        assert result == "Test message"

    @pytest.mark.asyncio
    async def test_message_to_string_with_list_content(self, generator):
        """Test converting message with list content to string"""
        message = {
            "role": "user",
            "content": [
                {"type": "text", "text": "Hello"},
                {"type": "text", "text": "world"},
            ]
        }
        result = generator._message_to_string(message)
        assert "Hello" in result
        assert "world" in result

    def test_default_llm_summary_threshold(self):
        """Test that default threshold is calculated correctly"""
        gen = SmartCompactMessageHistoryGenerator(
            max_tokens=100000,
            use_llm_summary=True,
        )
        # Should be None initially, calculated dynamically
        assert gen.llm_summary_threshold is None
        
        # When checking should_use_llm, it should use 70% of max_tokens
        root = Node.create("Test")
        for i in range(10):
            child = root.create_child()
            child.user_message = f"Message {i}"
            root = child
        
        gen.set_completion_model(Mock(spec=BaseCompletionModel))
        # At 71000 tokens (>70% of 100000), should trigger
        assert gen._should_use_llm_summary(71000, root) is True
        # At 69000 tokens (<70% of 100000), should not trigger
        assert gen._should_use_llm_summary(69000, root) is False

    @pytest.mark.asyncio
    async def test_generate_messages_uses_rule_based_first(self, generator, simple_node, workspace):
        """Test that generate_messages calls parent's implementation first"""
        with patch.object(
            SmartCompactMessageHistoryGenerator.__bases__[0],
            'generate_messages',
            new_callable=AsyncMock
        ) as mock_parent:
            mock_parent.return_value = [{"role": "user", "content": "test"}]
            
            await generator.generate_messages(simple_node, workspace)
            
            # Should call parent's generate_messages
            mock_parent.assert_called_once()

    def test_inheritance(self):
        """Test that SmartCompactMessageHistoryGenerator inherits from CompactMessageHistoryGenerator"""
        from moatless.message_history.compact import CompactMessageHistoryGenerator
        
        gen = SmartCompactMessageHistoryGenerator()
        assert isinstance(gen, CompactMessageHistoryGenerator)

    @pytest.mark.asyncio
    async def test_get_messages_since_last_summary_no_summary(self, generator):
        """Test getting messages when there's no summary"""
        from moatless.message_history.compact import NodeMessage
        
        messages = [
            NodeMessage(user_message="Message 1"),
            NodeMessage(assistant_message="Response 1"),
            NodeMessage(user_message="Message 2"),
        ]
        
        result = generator._get_messages_since_last_summary(messages)
        assert len(result) == 3
        assert result == messages

    @pytest.mark.asyncio
    async def test_get_messages_since_last_summary_with_summary(self, generator):
        """Test getting messages since last summary"""
        from moatless.message_history.compact import NodeMessage
        
        messages = [
            NodeMessage(user_message="Message 1"),
            NodeMessage(assistant_message="[SUMMARY]\nOld summary"),
            NodeMessage(user_message="Message 2"),
            NodeMessage(assistant_message="Response 2"),
        ]
        
        result = generator._get_messages_since_last_summary(messages)
        
        # Should include first message and messages since summary
        assert len(result) == 4  # first + summary + 2 after
        assert result[0].user_message == "Message 1"
        assert "[SUMMARY]" in (result[1].assistant_message or "")
