from pydantic import BaseModel, Field


class TopicMapNode(BaseModel):
    name: str = Field(description="Node display name")
    node_type: str = Field(
        description="One of: root, problem, method, mechanism, paper, idea, experiment, risk, open_question"
    )
    summary: str = Field(description="Brief description of this node")
    heat: str = Field(default="medium", description="low/medium/high/rising")
    maturity: str = Field(
        default="emerging", description="emerging/developing/mature/declining"
    )
    evidence_strength: str = Field(
        default="weak", description="weak/medium/strong"
    )


class TopicMapEdge(BaseModel):
    source: str = Field(
        description="Name of the source node (must match a node name above)"
    )
    target: str = Field(
        description="Name of the target node (must match a node name above)"
    )
    relation: str = Field(
        default="parent_of",
        description="One of: supports, addresses, extends, contradicts, transfers_to, parent_of",
    )


class TopicMapOutput(BaseModel):
    nodes: list[TopicMapNode] = Field(
        description="List of mind map nodes (at least 5)"
    )
    edges: list[TopicMapEdge] = Field(
        description="List of directed edges connecting nodes"
    )
    open_questions: list[str] = Field(
        default_factory=list,
        description="Key open questions in this research area",
    )
    search_queries: list[str] = Field(
        default_factory=list,
        description="Suggested search queries for paper retrieval",
    )
