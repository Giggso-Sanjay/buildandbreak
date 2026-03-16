import { useState, useEffect, useCallback } from "react";
import { AnimatePresence } from "framer-motion";
import { WelcomeScreen } from "./components/WelcomeScreen";
import { Header } from "./components/Header";
import { ChatMessage } from "./components/ChatMessage";
import { TypingIndicator } from "./components/TypingIndicator";
import { ChatInput } from "./components/ChatInput";
import { UploadModal } from "./components/UploadModal";
import { sendChatMessage } from "./api/chat";
import { parseMLData } from "./utils/parseMLData";
import { isMLPerformanceQuery } from "./hooks/useMLQueryDetection";

const TRINITY_PROMPT =
  "Please provide the necessary Datadrift and Observability files from Trinity to proceed.";

const NO_DATASOURCE_PROMPT =
  "Please upload a datasource before sending a query.";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
}

export default function App() {
  const [showWelcome, setShowWelcome] = useState(true);
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [uploadedFiles, setUploadedFiles] = useState<File[]>([]);
  const [hasDatadriftAndObservability, setHasDatadriftAndObservability] =
    useState(false);

  // Auto-transition from welcome to chat after 3 seconds
  useEffect(() => {
    const t = setTimeout(() => setShowWelcome(false), 3000);
    return () => clearTimeout(t);
  }, []);

  // Validate Trinity files when uploads change
  useEffect(() => {
    if (uploadedFiles.length === 0) {
      setHasDatadriftAndObservability(false);
      return;
    }
    const readFiles = async () => {
      const contents = await Promise.all(
        uploadedFiles.map((f) =>
          f.text().then((c) => ({ name: f.name, content: c }))
        )
      );
      const parsed = parseMLData(contents);
      const ok =
        parsed.datadrift?.isValid === true &&
        parsed.observability?.isValid === true;
      setHasDatadriftAndObservability(ok);
    };
    readFiles();
  }, [uploadedFiles]);

  const handleFilesSelected = useCallback((files: File[]) => {
    setUploadedFiles((prev) => {
      const names = new Set(prev.map((f) => f.name));
      const added = files.filter((f) => !names.has(f.name));
      return [...prev, ...added];
    });
  }, []);

  const handleClearSession = useCallback(() => {
    setUploadedFiles([]);
    setMessages([]);
  }, []);

  const handleSend = useCallback(
    async (text: string) => {
      // Block if no datasource uploaded
      if (uploadedFiles.length === 0) {
        setMessages((prev) => [
          ...prev,
          { id: crypto.randomUUID(), role: "user", content: text },
          {
            id: crypto.randomUUID(),
            role: "assistant",
            content: NO_DATASOURCE_PROMPT,
          },
        ]);
        return;
      }
      // Trinity validation: if ML query, require both files
      if (isMLPerformanceQuery(text) && !hasDatadriftAndObservability) {
        setMessages((prev) => [
          ...prev,
          { id: crypto.randomUUID(), role: "user", content: text },
          {
            id: crypto.randomUUID(),
            role: "assistant",
            content: TRINITY_PROMPT,
          },
        ]);
        return;
      }

      const userMsg: Message = {
        id: crypto.randomUUID(),
        role: "user",
        content: text,
      };
      setMessages((prev) => [...prev, userMsg]);
      setIsLoading(true);

      try {
        const res = await sendChatMessage(text);
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            role: "assistant",
            content: res.reply,
          },
        ]);
      } catch (err) {
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            role: "assistant",
            content: `Error: ${err instanceof Error ? err.message : "Failed to get response"}`,
          },
        ]);
      } finally {
        setIsLoading(false);
      }
    },
    [uploadedFiles.length, hasDatadriftAndObservability]
  );

  return (
    <>
      <AnimatePresence mode="wait">
        {showWelcome ? (
          <WelcomeScreen key="welcome" />
        ) : (
          <div
            key="chat"
            className="flex min-h-screen flex-col bg-neutral-50 dark:bg-neutral-950"
          >
            <Header onUploadClick={() => setUploadModalOpen(true)} />
            <main className="flex-1 overflow-y-auto pb-20 pt-4">
              <div className="mx-auto max-w-3xl">
                <AnimatePresence>
                  {messages.map((m, i) => (
                    <ChatMessage
                      key={m.id}
                      role={m.role}
                      content={m.content}
                      index={i}
                    />
                  ))}
                  {isLoading && <TypingIndicator />}
                </AnimatePresence>
              </div>
            </main>
            <div className="fixed bottom-0 left-0 right-0 z-30 flex items-center gap-4 border-t border-neutral-200 bg-white/80 px-4 py-4 backdrop-blur-sm dark:border-neutral-800 dark:bg-neutral-950/80">
              {/* Clear session - left bottom */}
              <button
                type="button"
                onClick={handleClearSession}
                className="shrink-0 rounded-full border border-neutral-300 px-4 py-2 text-sm font-medium text-neutral-600 transition-colors hover:bg-neutral-100 hover:text-neutral-800 dark:border-neutral-600 dark:text-neutral-400 dark:hover:bg-neutral-800 dark:hover:text-neutral-200"
              >
                Clear session
              </button>
              {/* Input bar - centered in remaining space */}
              <div className="flex flex-1 justify-center min-w-0">
                <ChatInput onSend={handleSend} disabled={isLoading} />
              </div>
            </div>
          </div>
        )}
      </AnimatePresence>

      <UploadModal
        isOpen={uploadModalOpen}
        onClose={() => setUploadModalOpen(false)}
        onFilesSelected={handleFilesSelected}
        uploadedFiles={uploadedFiles}
      />
    </>
  );
}
