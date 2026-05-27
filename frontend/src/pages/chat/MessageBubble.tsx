import ReactMarkdown from "react-markdown";

interface Props {
  message: { id: string; role: string; content: string; agent_name: string | null; review_status: string | null; };
}

interface ReviewCard {
  summary: string;
  correctness: string;
  score: number;
  action: string;
  issues: string[];
}

function parseReviewCard(text: string): { review: ReviewCard; before: string; after: string } | null {
  const match = text.match(/\[REVIEW\]\s*\n([\s\S]*?)\n\s*\[\/REVIEW\]/);
  if (!match) return null;

  const body = match[1];
  const before = text.slice(0, match.index!).trim();
  const after = text.slice(match.index! + match[0].length).trim();

  const field = (key: string) => body.match(new RegExp(`^${key}:\\s*(.+)$`, "m"))?.[1]?.trim();
  const list = (key: string) => {
    const lm = body.match(new RegExp(`^${key}:\\s*\\n((?:\\s*-\\s*.+\\n?)*)`, "m"));
    if (!lm) return [];
    return [...lm[1].matchAll(/^\s*-\s*(.+)$/gm)].map((m) => m[1].trim());
  };

  const summary = field("summary");
  const correctness = field("correctness");
  const scoreStr = field("score");
  const action = field("action");
  const issues = list("issues");

  if (!summary || !correctness || !scoreStr || !action) return null;
  const score = parseInt(scoreStr);
  if (isNaN(score) || score < 1 || score > 5) return null;

  return { review: { summary, correctness, score, action, issues }, before, after };
}

const ReviewCardView: React.FC<{ review: ReviewCard }> = ({ review }) => {
  const statusColor = review.correctness === "pass" ? "#07C160" : "#FF5252";
  const statusText = review.correctness === "pass" ? "审查通过" : "审查不通过";
  const statusIcon = review.correctness === "pass" ? "✓" : "✗";
  const actionMap: Record<string, string> = { accept: "已通过", redo: "已要求重做", supplement: "已补充" };

  return (
    <div className="rounded border border-secondary/30 bg-secondary/10 p-3 my-2 text-sm">
      <div className="flex items-center gap-2 mb-2">
        <span className="w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-bold" style={{ backgroundColor: statusColor }}>
          {statusIcon}
        </span>
        <span style={{ color: statusColor }} className="font-bold">{statusText}</span>
      </div>

      <div className="space-y-1">
        <div className="text-yellow-500">
          {"★".repeat(review.score)}{"☆".repeat(5 - review.score)} {review.score}/5
        </div>
        <div className="text-primary font-bold">{review.summary}</div>
        {review.issues.length > 0 && review.issues[0] !== "none" && (
          <div className="space-y-0.5 mt-1">
            {review.issues.map((issue, i) => (
              <div key={i} className="text-red-500 dark:text-red-400">• {issue}</div>
            ))}
          </div>
        )}
        {review.action && (
          <div className="text-secondary text-xs mt-1">→ {actionMap[review.action] || review.action}</div>
        )}
      </div>
    </div>
  );
};

const AVATAR_COLORS: Record<string, string> = { user: "#2196F3", "Topic Agent": "#07C160", "Paper Agent": "#F9A825" };

const MessageBubble: React.FC<Props> = ({ message }) => {
  const { role, content, agent_name, review_status } = message;
  const isUser = role === "user";
  const isSystem = role === "system";
  const displayName = isUser ? "我" : (agent_name || "System");
  const color = AVATAR_COLORS[displayName] || "#757575";

  if (isSystem) {
    return <div className="text-center text-secondary text-xs py-1">{content}</div>;
  }

  // Check for review card rendering
  const reviewData = !isUser ? parseReviewCard(content) : null;

  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : ""}`}>
      <div className="w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-bold shrink-0" style={{ backgroundColor: color }}>
        {displayName[0]}
      </div>
      <div className="flex flex-col max-w-[70%]">
        <span className={`text-xs text-secondary mb-0.5 ${isUser ? "text-right" : ""}`}>
          {displayName}
          {review_status === "passed" && " · 审查通过"}
          {review_status === "failed" && " · 审查未通过"}
        </span>
        <div
          className={`rounded-lg px-3 py-2 text-sm ${
            isUser
              ? "bg-[#07C160] text-white"
              : "bg-[#F0F0F0] dark:bg-[#2a2a2a] text-primary border border-secondary/20"
          }`}
        >
          {reviewData ? (
            <>
              {reviewData.before && <ReactMarkdown>{reviewData.before}</ReactMarkdown>}
              <ReviewCardView review={reviewData.review} />
              {reviewData.after && <ReactMarkdown>{reviewData.after}</ReactMarkdown>}
            </>
          ) : (
            <ReactMarkdown>{content}</ReactMarkdown>
          )}
        </div>
      </div>
    </div>
  );
};

export default MessageBubble;
