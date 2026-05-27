import React, { useState } from "react";

interface Props { onSend: (content: string) => void; disabled: boolean; }

const ChatInput: React.FC<Props> = ({ onSend, disabled }) => {
  const [value, setValue] = useState("");

  const handleSend = () => { if (!value.trim() || disabled) return; onSend(value.trim()); setValue(""); };

  return (
    <div className="border-t border-secondary p-3 flex gap-2">
      <input className="flex-1 border border-secondary rounded px-3 py-2 text-sm bg-primary text-primary focus:outline-none focus:border-accent"
        placeholder="输入消息... 使用 @Agent名称 指定 Agent" value={value}
        onChange={(e) => setValue(e.target.value)} onKeyDown={(e) => e.key === "Enter" && handleSend()} disabled={disabled} />
      <button className="px-4 py-2 bg-[#07C160] text-white rounded text-sm hover:bg-[#06AD56] disabled:opacity-50"
        onClick={handleSend} disabled={disabled || !value.trim()}>发送</button>
    </div>
  );
};

export default ChatInput;
