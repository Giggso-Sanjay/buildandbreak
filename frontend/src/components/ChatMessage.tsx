import { motion } from "framer-motion";

export type MessageRole = "user" | "assistant";

interface ChatMessageProps {
  role: MessageRole;
  content: string;
  index: number;
}

/**
 * Single chat message bubble - user right, bot left.
 * Gemini-style layout with subtle animations.
 */
export function ChatMessage({ role, content, index }: ChatMessageProps) {
  const isUser = role === "user";

  return (
    <motion.div
      className={`flex w-full px-4 py-2 ${isUser ? "justify-end" : "justify-start"}`}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: index * 0.05 }}
    >
      <div
        className={`max-w-[85%] rounded-2xl px-4 py-3 sm:max-w-[75%] ${
          isUser
            ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
            : "bg-neutral-100 text-neutral-900 dark:bg-neutral-800 dark:text-neutral-100"
        }`}
      >
        <p className="whitespace-pre-wrap text-sm leading-relaxed">{content}</p>
      </div>
    </motion.div>
  );
}
