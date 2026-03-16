import { motion } from "framer-motion";

/**
 * High-end welcome screen with Orca branding and pulse animation.
 * Auto-transitions to main chat after 3 seconds (handled by parent).
 */
export function WelcomeScreen() {
  return (
    <motion.div
      className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-neutral-50 dark:bg-neutral-950"
      initial={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.6, ease: "easeInOut" }}
    >
      {/* Subtle pulse animation on the Orca title */}
      <motion.h1
        className="text-5xl font-light tracking-tight text-neutral-900 dark:text-neutral-100 sm:text-6xl"
        animate={{
          opacity: [0.85, 1, 0.85],
          scale: [0.98, 1, 0.98],
        }}
        transition={{
          duration: 2,
          repeat: Infinity,
          ease: "easeInOut",
        }}
      >
        Orca
      </motion.h1>
      {/* Subtitle with fade */}
      <motion.p
        className="mt-3 text-sm text-neutral-500 dark:text-neutral-400"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.5, duration: 0.5 }}
      >
        AI-powered insights
      </motion.p>
    </motion.div>
  );
}
