import { useEffect, useRef } from "react";
import { useChatStore } from "../../hooks/store";
import { api } from "../../api/client";
import MessageBubble from "./MessageBubble";
import ChatInput from "./ChatInput";
import { message } from "antd";

const ChatView: React.FC<{ sessionId: string }> = ({ sessionId }) => {
  const { messages, setMessages, addMessage, streaming, setStreaming, pendingAgents, setPendingAgents } = useChatStore();
  const scrollRef = useRef<HTMLDivElement>(null);
  const [messageApi, contextHolder] = message.useMessage();

  useEffect(() => { loadMessages(); }, [sessionId]);
  useEffect(() => { scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight); }, [messages, pendingAgents]);

  const loadMessages = async () => {
    try { setMessages(await api.listMessages(sessionId)); } catch { /* */ }
  };

  const handleSend = async (content: string) => {
    setStreaming(true);
    try {
      const response = await api.sendMessage({ session_id: sessionId, content });
      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) return;

      let buffer = "";
      let currentEvent = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("event: ")) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            try {
              const payload = JSON.parse(line.slice(6));
              if (currentEvent === "status") {
                setPendingAgents(payload);
              } else {
                // "message" event — add to messages
                addMessage(payload);
              }
            } catch { /* skip malformed JSON */ }
          }
          // Empty line = event separator, reset
          if (line === "") currentEvent = "";
        }
      }
    } catch { messageApi.error("发送失败"); }
    finally {
      setStreaming(false);
      setPendingAgents([]);
      await loadMessages(); // Final refresh to ensure consistency
    }
  };

  return (
    <div className="flex flex-col h-full">
      {contextHolder}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.map((msg) => <MessageBubble key={msg.id} message={msg} />)}
        {pendingAgents.length > 0 && (
          <div className="text-secondary text-sm italic px-4">
            {pendingAgents.map((a) => (
              <span key={a.agent_name} className="mr-3">
                {a.state === "running" ? "⏳" : "⏱"} {a.agent_name} {a.state === "running" ? "思考中..." : "排队中"}
              </span>
            ))}
          </div>
        )}
      </div>
      <ChatInput onSend={handleSend} disabled={streaming} />
    </div>
  );
};

export default ChatView;
