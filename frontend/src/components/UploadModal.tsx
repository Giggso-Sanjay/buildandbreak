import { useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";

interface UploadModalProps {
  isOpen: boolean;
  onClose: () => void;
  onFilesSelected: (files: File[]) => void;
  uploadedFiles: File[];
}

/**
 * Modal for uploading JSON datasources (Trinity datadrift + observability).
 */
export function UploadModal({
  isOpen,
  onClose,
  onFilesSelected,
  uploadedFiles,
}: UploadModalProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []).filter(
      (f) => f.name.toLowerCase().endsWith(".json")
    );
    if (files.length) onFilesSelected(files);
    e.target.value = "";
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />
          {/* Modal */}
          <motion.div
            className="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-neutral-200 bg-white p-6 shadow-xl dark:border-neutral-700 dark:bg-neutral-900"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: 0.2 }}
          >
            <h2 className="text-lg font-medium text-neutral-900 dark:text-neutral-100">
              Upload Datasources
            </h2>
            <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
              Upload JSON files (datadrift response and observability from Trinity).
            </p>
            <input
              ref={inputRef}
              type="file"
              accept=".json"
              multiple
              onChange={handleChange}
              className="hidden"
            />
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              className="mt-4 w-full rounded-full border-2 border-dashed border-neutral-300 py-4 text-sm font-medium text-neutral-600 transition-colors hover:border-neutral-400 hover:text-neutral-800 dark:border-neutral-600 dark:text-neutral-400 dark:hover:border-neutral-500 dark:hover:text-neutral-200"
            >
              Choose JSON files
            </button>
            {uploadedFiles.length > 0 && (
              <ul className="mt-4 space-y-2">
                {uploadedFiles.map((f) => (
                  <li
                    key={f.name}
                    className="rounded-lg bg-neutral-100 px-3 py-2 text-sm text-neutral-700 dark:bg-neutral-800 dark:text-neutral-300"
                  >
                    {f.name}
                  </li>
                ))}
              </ul>
            )}
            <button
              type="button"
              onClick={onClose}
              className="mt-6 w-full rounded-full bg-neutral-900 py-2 text-sm font-medium text-white dark:bg-neutral-100 dark:text-neutral-900"
            >
              Done
            </button>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
