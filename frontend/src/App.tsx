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

  const handleSend = useCallback(
    async (text: string) => {
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
    [hasDatadriftAndObservability]
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
            <main className="flex-1 overflow-y-auto pb-24 pt-4">
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
            <ChatInput onSend={handleSend} disabled={isLoading} />
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
