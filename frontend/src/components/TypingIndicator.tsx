import { motion } from "framer-motion";

/**
 * Shimmering/typing animation shown while waiting for bot response.
 */
export function TypingIndicator() {
  return (
    <motion.div
      className="flex w-full justify-start px-4 py-2"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      <div className="flex items-center gap-1.5 rounded-2xl bg-neutral-100 px-4 py-3 dark:bg-neutral-800">
        {/* Three animated dots */}
        {[0, 1, 2].map((i) => (
          <motion.span
            key={i}
            className="h-2 w-2 rounded-full bg-neutral-500 dark:bg-neutral-400"
            animate={{
              opacity: [0.4, 1, 0.4],
              scale: [0.9, 1.1, 0.9],
            }}
            transition={{
              duration: 1.2,
              repeat: Infinity,
              delay: i * 0.2,
            }}
          />
        ))}
      </div>
    </motion.div>
  );
}
