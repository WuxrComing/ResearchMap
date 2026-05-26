import uuid
from unittest.mock import MagicMock, patch
from app.agents.topic_builder import TopicBuilder
from app.agents.schemas import TopicMapOutput, TopicMapNode, TopicMapEdge


def test_topic_map_output_validation():
    output = TopicMapOutput(
        nodes=[
            TopicMapNode(name="Root", node_type="root", summary="Core topic"),
            TopicMapNode(name="Problem 1", node_type="problem", summary="Key challenge"),
        ],
        edges=[
            TopicMapEdge(source="Root", target="Problem 1", relation="parent_of"),
        ],
        open_questions=["What remains unsolved?"],
        search_queries=["test query"],
    )
    assert len(output.nodes) == 2
    assert output.nodes[0].name == "Root"
    assert output.edges[0].source == "Root"


@patch("app.agents.topic_builder.LLMService")
def test_topic_builder_with_mock_llm(mock_llm_class):
    mock_output = TopicMapOutput(
        nodes=[
            TopicMapNode(name="Test Root", node_type="root", summary="Root node"),
            TopicMapNode(name="Test Problem", node_type="problem", summary="A problem"),
            TopicMapNode(name="Test Method", node_type="method", summary="A method"),
        ],
        edges=[
            TopicMapEdge(source="Test Root", target="Test Problem", relation="parent_of"),
            TopicMapEdge(source="Test Root", target="Test Method", relation="parent_of"),
        ],
        open_questions=[],
        search_queries=[],
    )

    mock_instance = mock_llm_class.return_value
    mock_instance.call_structured.return_value = (mock_output, [])

    builder = TopicBuilder()
    topic_id = uuid.uuid4().hex
    session_id = uuid.uuid4().hex

    node_count, edge_count, errors = builder.build(
        topic_id, "Test Topic", "Description", session_id
    )

    assert errors == []
    assert node_count == 3
    assert edge_count == 2
    mock_instance.call_structured.assert_called_once()


@patch("app.agents.topic_builder.LLMService")
def test_topic_builder_handles_failure(mock_llm_class):
    mock_instance = mock_llm_class.return_value
    mock_instance.call_structured.return_value = (None, ["Validation error"])

    builder = TopicBuilder()
    node_count, edge_count, errors = builder.build(
        uuid.uuid4().hex, "Bad Topic", "", uuid.uuid4().hex
    )

    assert node_count == 0
    assert edge_count == 0
    assert len(errors) == 1
    assert "Validation error" in errors[0]
