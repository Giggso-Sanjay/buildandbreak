import { useState, type FormEvent } from "react";
import { motion } from "framer-motion";

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
}

/**
 * Pill-shaped floating input bar at bottom center.
 * Gemini-style chat input.
 */
export function ChatInput({ onSend, disabled }: ChatInputProps) {
  const [value, setValue] = useState("");

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const trimmed = value.trim();
    if (trimmed && !disabled) {
      onSend(trimmed);
      setValue("");
    }
  };

  return (
    <motion.div
      className="fixed bottom-0 left-0 right-0 z-30 flex justify-center border-t border-neutral-200 bg-white/80 px-4 py-4 backdrop-blur-sm dark:border-neutral-800 dark:bg-neutral-950/80"
      initial={{ y: 20, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.3, delay: 0.1 }}
    >
      <form
        onSubmit={handleSubmit}
        className="flex w-full max-w-2xl items-center gap-2 rounded-full border border-neutral-200 bg-neutral-50 px-4 py-2 dark:border-neutral-700 dark:bg-neutral-900"
      >
        <input
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Message Orca..."
          disabled={disabled}
          className="flex-1 bg-transparent text-sm text-neutral-900 placeholder-neutral-500 outline-none dark:text-neutral-100 dark:placeholder-neutral-400 disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={disabled || !value.trim()}
          className="rounded-full bg-neutral-900 px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900"
        >
          Send
        </button>
      </form>
    </motion.div>
  );
}
