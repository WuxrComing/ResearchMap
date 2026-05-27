import React from "react";
import ReactMarkdown from "react-markdown";

interface Props {
  message: { id: string; role: string; content: string; agent_name: string | null; review_status: string | null; };
}

const AVATAR_COLORS: Record<string, string> = { user: "#2196F3", "Topic Agent": "#07C160", "Paper Agent": "#F9A825" };

const MessageBubble: React.FC<Props> = ({ message }) => {
  const { role, content, agent_name } = message;
  const isUser = role === "user";
  const isSystem = role === "system";
  const displayName = isUser ? "我" : (agent_name || "System");
  const color = AVATAR_COLORS[displayName] || "#757575";

  if (isSystem) return <div className="text-center text-secondary text-xs py-1">{content}</div>;

  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : ""}`}>
      <div className="w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-bold shrink-0" style={{ backgroundColor: color }}>{displayName[0]}</div>
      <div className="flex flex-col max-w-[70%]">
        <span className={`text-xs text-secondary mb-0.5 ${isUser ? "text-right" : ""}`}>{displayName}</span>
        <div className={`rounded-lg px-3 py-2 text-sm ${isUser ? "bg-[#07C160] text-white" : "bg-[#F0F0F0] dark:bg-[#2a2a2a] text-primary border border-secondary/20"}`}>
          <ReactMarkdown>{content}</ReactMarkdown>
        </div>
      </div>
    </div>
  );
};

export default MessageBubble;
