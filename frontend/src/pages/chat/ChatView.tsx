import { useEffect, useRef, useState, useCallback } from "react";
import { useChatStore } from "../../hooks/store";
import { api } from "../../api/client";
import MessageBubble from "./MessageBubble";
import ChatInput from "./ChatInput";
import { message } from "antd";

const PAGE_SIZE = 20;

const ChatView: React.FC<{ sessionId: string }> = ({ sessionId }) => {
  const { messages, setMessages, addMessage, streaming, setStreaming, pendingAgents, setPendingAgents } = useChatStore();
  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [messageApi, contextHolder] = message.useMessage();
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const allMessages = useRef<any[]>([]);
  const userScrolledUp = useRef(false);

  // Load all messages, but only display latest PAGE_SIZE
  const loadMessages = async () => {
    try {
      const data = await api.listMessages(sessionId);
      allMessages.current = data;
      setHasMore(data.length > PAGE_SIZE);
      // Show latest PAGE_SIZE messages
      setMessages(data.slice(-PAGE_SIZE));
    } catch { /* */ }
  };

  useEffect(() => { loadMessages(); }, [sessionId]);

  // Auto-scroll to bottom when messages change (unless user scrolled up)
  useEffect(() => {
    if (!userScrolledUp.current) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, pendingAgents]);

  // Detect user scroll to load more
  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el || loadingMore || !hasMore) return;

    // Track if user scrolled up
    const isAtBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 60;
    userScrolledUp.current = !isAtBottom;

    // Load more when scrolling near top
    if (el.scrollTop < 40) {
      const currentVisible = messages.length;
      const startIdx = Math.max(0, allMessages.current.length - currentVisible - PAGE_SIZE);
      if (startIdx < allMessages.current.length - currentVisible) {
        setLoadingMore(true);
        const moreMessages = allMessages.current.slice(
          Math.max(0, allMessages.current.length - currentVisible - PAGE_SIZE),
          allMessages.current.length - currentVisible
        );
        // Prepend older messages
        const prevHeight = el.scrollHeight;
        const combined = [...moreMessages, ...messages] as any;
        setMessages(combined);
        setHasMore(startIdx > 0);
        // Maintain scroll position
        requestAnimationFrame(() => {
          el.scrollTop = el.scrollHeight - prevHeight;
          setLoadingMore(false);
        });
      }
    }
  }, [loadingMore, hasMore, messages.length]);

  const handleSend = async (content: string) => {
    setStreaming(true);
    userScrolledUp.current = false; // force scroll to bottom on send
    try {
      const response = await api.sendMessage({ session_id: sessionId, content });
      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) return;

      let buffer = "", currentEvent = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          if (line.startsWith("event: ")) { currentEvent = line.slice(7).trim(); continue; }
          if (!line.startsWith("data: ")) continue;
          try {
            const payload = JSON.parse(line.slice(6));
            if (currentEvent === "status") setPendingAgents(payload);
            else { addMessage(payload); allMessages.current.push(payload); }
          } catch { /* */ }
        }
      }
    } catch { messageApi.error("发送失败"); }
    finally {
      setStreaming(false);
      setPendingAgents([]);
      await loadMessages();
    }
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {contextHolder}
      <div ref={scrollRef} onScroll={handleScroll} className="flex-1 overflow-y-auto scroll p-4 space-y-3">
        {hasMore && <div className="text-center text-secondary text-xs py-2">向上滚动加载更多...</div>}
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
        <div ref={bottomRef} />
      </div>
      <ChatInput onSend={handleSend} disabled={streaming} />
    </div>
  );
};

export default ChatView;
