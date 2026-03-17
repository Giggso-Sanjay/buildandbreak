import { useState, useEffect, useCallback } from "react";
import { AnimatePresence } from "framer-motion";

/**
 * Fallback for crypto.randomUUID()
 * crypto.randomUUID() is only available in Secure Contexts (HTTPS or localhost).
 * AWS deployments over HTTP will crash without this fallback.
 */
function generateUUID() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}
import { WelcomeScreen } from "./components/WelcomeScreen";
import { Header } from "./components/Header";
import { ChatMessage } from "./components/ChatMessage";
import { TypingIndicator } from "./components/TypingIndicator";
import { ChatInput } from "./components/ChatInput";
import { UploadModal } from "./components/UploadModal";
import { sendChatMessage, clearSession, uploadKB } from "./api/chat";
import { parseMLData } from "./utils/parseMLData";
import { isMLPerformanceQuery } from "./hooks/useMLQueryDetection";

const KB_PROMPT =
  "Please upload the ml_knowledge_base.json file to generate a response.";

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
  const [hasKB, setHasKB] = useState(false);

  // Auto-transition from welcome to chat after 3 seconds
  useEffect(() => {
    const t = setTimeout(() => setShowWelcome(false), 3000);
    return () => clearTimeout(t);
  }, []);

  // Validate KB file presence when uploads change
  useEffect(() => {
    if (uploadedFiles.length === 0) {
      setHasKB(false);
      return;
    }
    const checkKB = async () => {
      const files = uploadedFiles.map((f) => ({ name: f.name, content: "" }));
      const parsed = parseMLData(files);
      setHasKB(parsed.hasKB);
    };
    checkKB();
  }, [uploadedFiles]);

  const handleFilesSelected = useCallback(async (files: File[]) => {
    // Only keep the most recent JSON file to ensure a single-KB constraint
    const kbFile = [...files].reverse().find(f => f.name === "ml_knowledge_base.json") 
                || [...files].reverse().find(f => f.name.toLowerCase().endsWith(".json"));

    if (kbFile) {
      // Automatic session reset: clear messages and previous files
      setMessages([]);
      setUploadedFiles([kbFile]);
      
      try {
        const content = await kbFile.text();
        // We always send it as 'ml_knowledge_base.json' so the backend knows to treat it as the KB
        const res = await uploadKB([{ name: "ml_knowledge_base.json", content }]);
        if (res.status === "error") {
          // Add a message to the chat to notify the user of the validation error
          setMessages((prev) => [
            ...prev,
            {
              id: generateUUID(),
              role: "assistant",
              content: `⚠️ **Upload Failed**: ${res.message}`,
            },
          ]);
          // Reset uploaded files so user can try again
          setUploadedFiles([]);
        }
      } catch (err) {
        console.error("Failed to proactively upload KB:", err);
      }
    }
  }, []);

  const handleClearSession = useCallback(async () => {
    try {
      await clearSession();
    } catch {
      // Ignore clear-session API errors
    }
    setUploadedFiles([]);
    setMessages([]);
  }, []);

  const handleSend = useCallback(
    async (text: string) => {
      // Block if no datasource uploaded
      if (uploadedFiles.length === 0) {
        setMessages((prev) => [
          ...prev,
          { id: generateUUID(), role: "user", content: text },
          {
            id: generateUUID(),
            role: "assistant",
            content: NO_DATASOURCE_PROMPT,
          },
        ]);
        return;
      }
      // KB validation: if ML query, require ml_knowledge_base.json
      if (isMLPerformanceQuery(text) && !hasKB) {
        setMessages((prev) => [
          ...prev,
          { id: generateUUID(), role: "user", content: text },
          {
            id: generateUUID(),
            role: "assistant",
            content: KB_PROMPT,
          },
        ]);
        return;
      }

      const userMsg: Message = {
        id: generateUUID(),
        role: "user",
        content: text,
      };
      setMessages((prev) => [...prev, userMsg]);
      setIsLoading(true);

      try {
        // Since we proactively upload files in handleFilesSelected, we don't need to re-read
        // and re-send them here. This avoids "Stale Handle" errors in the browser.
        const datasources: any[] = []; 
        
        // Prepend context so nanobot uses tools (reads ml_knowledge_base.json)
        const messageWithContext = hasKB
            ? `[SYSTEM: You are the Model Risk Assessment Engine. 
1. DIRECTNESS: Jump immediately to the ML analysis. Do NOT provide intros, bios, or disclaimers about your specialization. 
2. SCOPE: ONLY facilitate Model Risk queries. If a query is NOT about ML performance, bias, drift, or metrics (e.g. general math), simply respond with: "I am designed only for Model Risk Assessment." 
3. TOOLS: If a tool reports 'unable to parse' or 'data not provided', simply state that those specific metrics are currently unavailable in the uploaded source.] ${text}`
            : text;
        const res = await sendChatMessage(messageWithContext, undefined, datasources);
        setMessages((prev) => [
          ...prev,
          {
            id: generateUUID(),
            role: "assistant",
            content: res.reply,
          },
        ]);
      } catch (err) {
        setMessages((prev) => [
          ...prev,
          {
            id: generateUUID(),
            role: "assistant",
            content: `Error: ${err instanceof Error ? err.message : "Failed to get response"}`,
          },
        ]);
      } finally {
        setIsLoading(false);
      }
    },
    [uploadedFiles, hasKB]
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
