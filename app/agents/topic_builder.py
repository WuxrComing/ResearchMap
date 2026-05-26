import uuid
from app.services.llm import LLMService
from app.services.mind_map_service import MindMapService
from app.agents.mind_map_tools import MIND_MAP_TOOLS, TOOL_SYSTEM_PROMPT
from app.models.chat_message import ChatMessage
from sqlmodel import Session
from app.services.storage import get_engine


class TopicBuilder:
    """Builds mind maps via LLM tool-calling instead of raw JSON."""

    def __init__(self):
        self.llm = LLMService()

    def build(
        self, topic_id: str, title: str, description: str, session_id: str
    ) -> tuple[int, int, list[str]]:
        service = MindMapService(topic_id)
        user_prompt = (
            f"Research Topic: {title}\n\n"
            f"Description: {description}\n\n"
            "Please build a comprehensive mind map for this topic. "
            "Start by adding a ROOT node, then expand with problem, method, mechanism, "
            "idea, experiment, risk, and open_question nodes. "
            "Connect them appropriately using parent_of edges for hierarchy "
            "and supports/extends/contradicts for cross-connections. "
            "Aim for 8-15 nodes with meaningful summaries."
        )

        tool_calls = self.llm.call_with_tools(
            system_prompt=TOOL_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            tools=MIND_MAP_TOOLS,
            temperature=0.3,
        )

        node_count = 0
        edge_count = 0
        errors = []
        id_map: dict[str, str] = {}  # LLM call ID → real node UUID

        if not isinstance(tool_calls, list):
            errors.append(f"Unexpected response type: {type(tool_calls)}")
            tool_calls = []

        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue
            name = tc.get("name", "")
            args = tc.get("arguments", {})
            if not isinstance(args, dict):
                args = {}
            call_id = tc.get("id", "")

            try:
                if name == "add_node":
                    nid = service.add_node(**args)
                    # Map LLM's call ID → real UUID (also map node name if provided)
                    if call_id:
                        id_map[call_id] = nid
                    if "name" in args:
                        # Find the node by name to support name-based edge references
                        pass
                    node_count += 1
                elif name == "add_edge":
                    # Resolve source/target: try call ID map first, then try as node name
                    for key in ("source_id", "target_id"):
                        ref = args.get(key, "")
                        if ref in id_map:
                            args[key] = id_map[ref]
                    service.add_edge(**args)
                    edge_count += 1
                elif name == "update_node":
                    if "node_id" in args and args["node_id"] in id_map:
                        args["node_id"] = id_map[args["node_id"]]
                    service.update_node(**args)
                elif name == "delete_node":
                    nid = args.get("node_id", "")
                    if nid in id_map:
                        nid = id_map[nid]
                    service.delete_node(nid)
                elif name == "get_map_state":
                    pass
                elif name == "error":
                    errors.append(args.get("message", "Unknown error"))
                elif name == "done":
                    pass
            except Exception as e:
                errors.append(f"{name}: {e}")

        # Save system message
        status = (
            f"课题「{title}」的思维导图已生成。\n"
            f"共 {node_count} 个节点，{edge_count} 条连接。"
        )
        if errors:
            status += f"\n警告：{'; '.join(errors)}"

        with Session(get_engine()) as db:
            db.add(ChatMessage(
                id=uuid.uuid4().hex, session_id=session_id,
                role="system", content=status,
            ))
            db.commit()

        return node_count, edge_count, errors

    def expand_node(
        self, topic_id: str, node_id: str, node_name: str,
        instruction: str, session_id: str,
    ) -> tuple[int, int, list[str]]:
        """Expand an existing node with child nodes."""
        service = MindMapService(topic_id)
        state = service.get_map_state()

        user_prompt = (
            f"Current mind map state:\n{state}\n\n"
            f"User wants to expand node '{node_name}' (id: {node_id}).\n"
            f"Instruction: {instruction}\n\n"
            "Use get_map_state first to understand the structure, "
            "then add new child nodes and connect them to the target node "
            "via parent_of edges. Return a coherent sub-tree of 2-5 nodes."
        )

        tool_calls = self.llm.call_with_tools(
            system_prompt=TOOL_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            tools=MIND_MAP_TOOLS,
            temperature=0.3,
        )

        node_count = 0
        edge_count = 0
        errors = []

        for tc in tool_calls:
            name = tc.get("name", "")
            args = tc.get("arguments", {})
            try:
                if name == "add_node":
                    service.add_node(**args)
                    node_count += 1
                elif name == "add_edge":
                    service.add_edge(**args)
                    edge_count += 1
                elif name == "get_map_state":
                    pass  # already have state
                elif name == "error":
                    errors.append(args.get("message", ""))
            except Exception as e:
                errors.append(f"{name}: {e}")

        return node_count, edge_count, errors
