import { motion } from "framer-motion";

interface HeaderProps {
  onUploadClick: () => void;
}

/**
 * Minimalist header: Orca on left, Upload Datasources on right.
 * Gemini-inspired clean aesthetic.
 */
export function Header({ onUploadClick }: HeaderProps) {
  return (
    <motion.header
      className="sticky top-0 z-40 flex h-14 items-center justify-between border-b border-neutral-200 bg-white/80 px-4 backdrop-blur-sm dark:border-neutral-800 dark:bg-neutral-950/80 sm:px-6"
      initial={{ y: -20, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.3 }}
    >
      {/* Orca branding - top left */}
      <h1 className="text-lg font-medium tracking-tight text-neutral-900 dark:text-neutral-100">
        Orca
      </h1>

      {/* Upload Datasources - top right */}
      <button
        type="button"
        onClick={onUploadClick}
        className="rounded-full bg-neutral-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-neutral-700 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-300"
      >
        Upload Datasources
      </button>
    </motion.header>
  );
}
