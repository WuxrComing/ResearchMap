"""LLM tool definitions for mind map manipulation (OpenAI function-calling format)."""

MIND_MAP_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "add_node",
            "description": "Add a new node to the mind map and return its node_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Node display name (unique)"},
                    "node_type": {
                        "type": "string",
                        "enum": ["root", "problem", "method", "mechanism",
                                 "paper", "idea", "experiment", "risk", "open_question"],
                        "description": "Type of the node"
                    },
                    "summary": {"type": "string", "description": "Brief description of this node"},
                    "heat": {"type": "string", "enum": ["low", "medium", "high", "rising"]},
                    "maturity": {"type": "string", "enum": ["emerging", "developing", "mature", "declining"]},
                    "evidence_strength": {"type": "string", "enum": ["weak", "medium", "strong"]},
                },
                "required": ["name", "node_type", "summary"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_edge",
            "description": "Connect two existing nodes with a directed edge.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source_id": {"type": "string", "description": "ID of the source node"},
                    "target_id": {"type": "string", "description": "ID of the target node"},
                    "relation": {
                        "type": "string",
                        "enum": ["parent_of", "supports", "addresses", "extends", "contradicts", "transfers_to"],
                        "description": "Relationship type. Use 'parent_of' for hierarchical parent→child."
                    },
                },
                "required": ["source_id", "target_id", "relation"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_node",
            "description": "Update properties of an existing node.",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_id": {"type": "string"},
                    "name": {"type": "string"},
                    "node_type": {
                        "type": "string",
                        "enum": ["root", "problem", "method", "mechanism",
                                 "paper", "idea", "experiment", "risk", "open_question"]
                    },
                    "summary": {"type": "string"},
                    "heat": {"type": "string", "enum": ["low", "medium", "high", "rising"]},
                    "maturity": {"type": "string", "enum": ["emerging", "developing", "mature", "declining"]},
                    "evidence_strength": {"type": "string", "enum": ["weak", "medium", "strong"]},
                },
                "required": ["node_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_node",
            "description": "Remove a node and its connected edges from the mind map.",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_id": {"type": "string", "description": "ID of the node to remove"}
                },
                "required": ["node_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_map_state",
            "description": "Get the current state of the mind map (all nodes and edges). Use this first if you need to understand the existing structure before making changes.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
]

TOOL_SYSTEM_PROMPT = """\
You are a research mind map builder. You have access to tools to manipulate a mind map.

Workflow:
1. Begin by creating the ROOT node (add_node with node_type="root")
2. Create child PROBLEM, METHOD, and MECHANISM nodes
3. Connect them with add_edge (relation="parent_of")
4. Add IDEA, EXPERIMENT, RISK, and OPEN_QUESTION nodes
5. Use cross-relations (supports/extends/contradicts) for non-hierarchical connections

Guidelines:
- Node names must be concise and unique
- A well-structured map has 8-20 nodes covering diverse aspects
- The root node should be the entry point
- Always provide meaningful summaries for each node
- Use node_type to categorize: root, problem, method, mechanism, paper, idea, experiment, risk, open_question
- Assign realistic heat/maturity/evidence_strength values

When expanding an existing node, use get_map_state first to understand current structure,
then add new child nodes and connect them via parent_of edges."""
