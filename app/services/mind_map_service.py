"""Mind map CRUD service. All operations are atomic and validated."""
import uuid
from datetime import datetime, UTC
from sqlmodel import Session, select
from app.services.storage import get_engine
from app.models.map_node import MapNode
from app.models.map_edge import MapEdge


class MindMapError(Exception):
    pass


class MindMapService:
    """Encapsulates all mind map mutations. Usable by both UI and LLM tools."""

    def __init__(self, topic_id: str):
        self.topic_id = topic_id

    # ---- Node operations ----

    def add_node(self, name: str, node_type: str = "idea",
                 summary: str = "", heat: str = "medium",
                 maturity: str = "emerging", evidence_strength: str = "weak",
                 **kwargs) -> str:
        """Add a node. Returns the new node_id."""
        if not name.strip():
            raise MindMapError("Node name required")
        node_id = uuid.uuid4().hex
        with Session(get_engine()) as db:
            node = MapNode(
                id=node_id, topic_id=self.topic_id, name=name.strip(),
                node_type=node_type, summary=summary, heat=heat,
                maturity=maturity, evidence_strength=evidence_strength,
            )
            db.add(node)
            db.commit()
        return node_id

    def update_node(self, node_id: str = "", **kwargs) -> bool:
        if "node_id" in kwargs:
            node_id = kwargs.pop("node_id")
        """Update node fields. Kwargs: name, node_type, summary, heat, maturity, evidence_strength."""
        allowed = {"name", "node_type", "summary", "heat", "maturity", "evidence_strength"}
        updates = {k: v for k, v in kwargs.items() if k in allowed and v}
        if not updates:
            return False
        with Session(get_engine()) as db:
            node = db.get(MapNode, node_id)
            if not node or node.topic_id != self.topic_id:
                raise MindMapError(f"Node {node_id} not found")
            for k, v in updates.items():
                setattr(node, k, v)
            node.updated_at = datetime.now(UTC)
            db.commit()
        return True

    def delete_node(self, node_id: str = "", **kwargs) -> bool:
        if "node_id" in kwargs:
            node_id = kwargs.pop("node_id")
        """Delete a node and its connected edges."""
        with Session(get_engine()) as db:
            node = db.get(MapNode, node_id)
            if not node or node.topic_id != self.topic_id:
                return False
            # Remove connected edges
            from sqlmodel import delete as sm_delete
            db.exec(sm_delete(MapEdge).where(
                (MapEdge.source_node_id == node_id) | (MapEdge.target_node_id == node_id)
            ))
            db.delete(node)
            db.commit()
        return True

    def get_node(self, node_id: str) -> dict | None:
        with Session(get_engine()) as db:
            node = db.get(MapNode, node_id)
            if not node or node.topic_id != self.topic_id:
                return None
            return self._node_to_dict(node)

    # ---- Edge operations ----

    def add_edge(self, source_id: str, target_id: str,
                 relation: str = "parent_of", **kwargs) -> str:
        """Connect two nodes. Returns edge_id."""
        with Session(get_engine()) as db:
            src = db.get(MapNode, source_id)
            tgt = db.get(MapNode, target_id)
            if not src or src.topic_id != self.topic_id:
                raise MindMapError(f"Source node {source_id} not found")
            if not tgt or tgt.topic_id != self.topic_id:
                raise MindMapError(f"Target node {target_id} not found")
            edge_id = uuid.uuid4().hex
            edge = MapEdge(
                id=edge_id, topic_id=self.topic_id,
                source_node_id=source_id, target_node_id=target_id,
                relation=relation,
            )
            db.add(edge)
            db.commit()
        return edge_id

    def delete_edge(self, edge_id: str) -> bool:
        with Session(get_engine()) as db:
            edge = db.get(MapEdge, edge_id)
            if not edge or edge.topic_id != self.topic_id:
                return False
            db.delete(edge)
            db.commit()
        return True

    # ---- Query operations ----

    def get_all_nodes(self) -> list[dict]:
        with Session(get_engine()) as db:
            nodes = db.exec(
                select(MapNode).where(
                    MapNode.topic_id == self.topic_id, MapNode.status == "active"
                )
            ).all()
            return [self._node_to_dict(n) for n in nodes]

    def get_all_edges(self) -> list[dict]:
        with Session(get_engine()) as db:
            edges = db.exec(
                select(MapEdge).where(MapEdge.topic_id == self.topic_id)
            ).all()
            return [self._edge_to_dict(e) for e in edges]

    def get_map_state(self) -> dict:
        """Full map state for LLM context."""
        return {
            "topic_id": self.topic_id,
            "nodes": self.get_all_nodes(),
            "edges": self.get_all_edges(),
        }

    def find_roots(self) -> list[dict]:
        """Find root nodes (nodes with no incoming parent_of edges)."""
        nodes = self.get_all_nodes()
        edges = self.get_all_edges()
        child_ids = {e["target_node_id"] for e in edges if e["relation"] == "parent_of"}
        return [n for n in nodes if n["id"] not in child_ids]

    # ---- Helpers ----

    @staticmethod
    def _node_to_dict(node) -> dict:
        return {
            "id": node.id, "name": node.name, "node_type": node.node_type,
            "summary": node.summary, "heat": node.heat,
            "maturity": node.maturity, "evidence_strength": node.evidence_strength,
        }

    @staticmethod
    def _edge_to_dict(edge) -> dict:
        return {
            "id": edge.id, "source_node_id": edge.source_node_id,
            "target_node_id": edge.target_node_id, "relation": edge.relation,
        }
