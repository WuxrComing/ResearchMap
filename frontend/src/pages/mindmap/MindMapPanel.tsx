import React, { useEffect, useRef } from "react";
import { api } from "../../api/client";

const MindMapPanel: React.FC<{ workspaceId: string }> = ({ workspaceId }) => {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.getMindmap(workspaceId).then((data) => {
      if (!containerRef.current || !data.nodes?.length) return;
      renderTree(containerRef.current, data.nodes, data.edges);
    });
  }, [workspaceId]);

  const renderTree = (container: HTMLDivElement, nodes: any[], edges: any[]) => {
    const childIds = new Set(edges.filter((e: any) => e.relation === "parent_of").map((e: any) => e.target_node_id));
    const roots = nodes.filter((n: any) => !childIds.has(n.id));

    const childrenMap: Record<string, any[]> = {};
    for (const e of edges) {
      if (e.relation === "parent_of") {
        if (!childrenMap[e.source_node_id]) childrenMap[e.source_node_id] = [];
        childrenMap[e.source_node_id].push(nodes.find((n: any) => n.id === e.target_node_id));
      }
    }

    const heatColors: Record<string, string> = { hot: "#FF5252", medium: "#FF9800", cold: "#2196F3", warm: "#4CAF50" };

    const renderNode = (node: any, depth: number = 0): HTMLElement => {
      const div = document.createElement("div");
      div.className = "flex items-center gap-2 py-1 cursor-pointer hover:bg-secondary/10 rounded px-1";
      div.style.paddingLeft = `${depth * 16 + 4}px`;
      const dot = document.createElement("span");
      dot.className = "w-2 h-2 rounded-full shrink-0";
      dot.style.backgroundColor = heatColors[node.heat] || "#999";
      const name = document.createElement("span");
      name.className = "text-sm text-primary truncate";
      name.textContent = node.name;
      div.appendChild(dot); div.appendChild(name);
      return div;
    };

    container.innerHTML = "";
    const title = document.createElement("div");
    title.className = "text-sm font-bold text-primary px-2 py-2 border-b border-secondary mb-1";
    title.textContent = `思维导图 (${nodes.length} 节点)`;
    container.appendChild(title);

    const walk = (nodeList: any[], depth: number) => {
      for (const node of nodeList) { if (!node) continue; container.appendChild(renderNode(node, depth)); walk(childrenMap[node.id] || [], depth + 1); }
    };
    walk(roots, 0);
  };

  return <div ref={containerRef} className="h-full overflow-y-auto scroll p-2 text-sm" />;
};

export default MindMapPanel;
