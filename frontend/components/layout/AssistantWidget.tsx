"use client";

import {
  MessageCircle,
  Mic,
  Plus,
  Send,
  Square,
  Volume2,
  X,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import { assistantApi } from "@/lib/api/client";
import type {
  AssistantConversation,
  AssistantLanguage,
  AssistantMessage,
} from "@/lib/types";

const LANGUAGES: { value: AssistantLanguage; label: string }[] = [
  { value: "auto", label: "Auto detect" },
  { value: "en", label: "English" },
  { value: "am", label: "Amharic" },
  { value: "om", label: "Afaan Oromoo" },
];

const LANGUAGE_TAGS: Record<Exclude<AssistantLanguage, "auto">, string> = {
  en: "en",
  am: "am",
  om: "om",
};

export function AssistantWidget() {
  const [open, setOpen] = useState(false);
  const [conversations, setConversations] = useState<AssistantConversation[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [language, setLanguage] = useState<AssistantLanguage>("auto");
  const [input, setInput] = useState("");
  const [loadingConversations, setLoadingConversations] = useState(false);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [sending, setSending] = useState(false);
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [error, setError] = useState("");
  const [voiceNotice, setVoiceNotice] = useState("");
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const cancelRecordingRef = useRef(false);

  const refreshConversations = useCallback(async () => {
    setLoadingConversations(true);
    try {
      const result = await assistantApi.conversations();
      setConversations(result.results);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Could not load assistant conversations."
      );
    } finally {
      setLoadingConversations(false);
    }
  }, []);

  useEffect(() => {
    if (open) void refreshConversations();
  }, [open, refreshConversations]);

  useEffect(() => {
    if (!open || !conversationId) {
      setMessages([]);
      return;
    }
    let cancelled = false;
    setLoadingMessages(true);
    setError("");
    assistantApi
      .messages(conversationId)
      .then((result) => {
        if (!cancelled) setMessages(result.results);
      })
      .catch((requestError: unknown) => {
        if (!cancelled) {
          setError(
            requestError instanceof Error
              ? requestError.message
              : "Could not load this conversation."
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingMessages(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, conversationId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (!("speechSynthesis" in window)) return;
    const updateVoices = () => setVoices(window.speechSynthesis.getVoices());
    updateVoices();
    window.speechSynthesis.addEventListener("voiceschanged", updateVoices);
    return () => {
      window.speechSynthesis.removeEventListener("voiceschanged", updateVoices);
      window.speechSynthesis.cancel();
    };
  }, []);

  useEffect(
    () => () => {
      cancelRecordingRef.current = true;
      if (recorderRef.current?.state === "recording") recorderRef.current.stop();
      streamRef.current?.getTracks().forEach((track) => track.stop());
    },
    []
  );

  async function startConversation() {
    setError("");
    try {
      const conversation = await assistantApi.createConversation(language);
      setConversations((current) => [conversation, ...current]);
      setConversationId(conversation.id);
      setMessages([]);
      setLanguage(conversation.language);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Could not start a conversation."
      );
    }
  }

  function selectConversation(id: string) {
    const selected = conversations.find((item) => item.id === id);
    setConversationId(id);
    if (selected) setLanguage(selected.language);
  }

  async function sendMessage(event?: FormEvent) {
    event?.preventDefault();
    const content = input.trim();
    if (!content || sending || transcribing) return;
    setError("");
    setSending(true);
    setInput("");
    try {
      let id = conversationId;
      if (!id) {
        const conversation = await assistantApi.createConversation(language);
        id = conversation.id;
        setConversationId(id);
        setConversations((current) => [conversation, ...current]);
      }
      const result = await assistantApi.sendMessage(id, content, language);
      setMessages((current) => [
        ...current,
        result.user_message,
        result.assistant_message,
      ]);
      void refreshConversations();
    } catch (requestError) {
      setInput(content);
      setError(
        requestError instanceof Error
          ? requestError.message
          : "The message could not be sent."
      );
    } finally {
      setSending(false);
    }
  }

  function handleInputKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void sendMessage();
    }
  }

  async function startRecording() {
    setError("");
    setVoiceNotice("");
    if (
      !navigator.mediaDevices?.getUserMedia ||
      typeof MediaRecorder === "undefined"
    ) {
      setVoiceNotice("Voice recording is unavailable in this browser. You can type instead.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mimeType = [
        "audio/webm;codecs=opus",
        "audio/webm",
        "audio/mp4",
      ].find((type) => MediaRecorder.isTypeSupported(type));
      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);
      const chunks: Blob[] = [];
      recorder.addEventListener("dataavailable", (event) => {
        if (event.data.size) chunks.push(event.data);
      });
      recorder.addEventListener("error", () => {
        cancelRecordingRef.current = true;
        setError("The recording failed. Please try again or type your message.");
        setRecording(false);
        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
      });
      recorder.addEventListener("stop", () => {
        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        setRecording(false);
        if (cancelRecordingRef.current) {
          cancelRecordingRef.current = false;
          return;
        }
        const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
        if (!blob.size) {
          setVoiceNotice("No audio was captured. Please try again or type your message.");
          return;
        }
        const extension = recorder.mimeType.includes("mp4") ? "mp4" : "webm";
        const audio = new File([blob], `assistant-recording.${extension}`, {
          type: recorder.mimeType || "audio/webm",
        });
        void transcribeRecording(audio);
      });
      recorderRef.current = recorder;
      cancelRecordingRef.current = false;
      recorder.start();
      setRecording(true);
    } catch {
      setVoiceNotice(
        "Microphone access was not available. Check browser permission or type your message."
      );
    }
  }

  async function transcribeRecording(audio: File) {
    setTranscribing(true);
    setError("");
    try {
      const result = await assistantApi.transcribe(audio, language);
      setInput(result.text);
      setVoiceNotice("Review the transcript before sending. Recognition may vary by language.");
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Voice transcription failed. You can type your message instead."
      );
    } finally {
      setTranscribing(false);
    }
  }

  function speakMessage(content: string) {
    if (!("speechSynthesis" in window)) {
      setVoiceNotice("Speech playback is unavailable in this browser. The text remains available.");
      return;
    }
    if (language === "auto") {
      setVoiceNotice("Choose a language to check for a matching installed browser voice.");
      return;
    }
    const languageTag = LANGUAGE_TAGS[language];
    const voice = voices.find((item) =>
      item.lang.toLowerCase().startsWith(languageTag)
    );
    if (!voice) {
      setVoiceNotice(
        `No matching ${LANGUAGES.find((item) => item.value === language)?.label} voice is installed. You can read the reply as text.`
      );
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(content);
    utterance.voice = voice;
    utterance.lang = voice.lang;
    window.speechSynthesis.speak(utterance);
  }

  function closeAssistant() {
    if (recorderRef.current?.state === "recording") {
      cancelRecordingRef.current = true;
      recorderRef.current.stop();
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      setRecording(false);
    }
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    setOpen(false);
  }

  async function deleteConversation() {
    if (!conversationId) return;
    const confirmDelete = window.confirm("Delete this conversation and its messages?");
    if (!confirmDelete) return;
    try {
      await assistantApi.deleteConversation(conversationId);
      setConversations((current) =>
        current.filter((conversation) => conversation.id !== conversationId)
      );
      setConversationId(null);
      setMessages([]);
      setLanguage("auto");
      setError("");
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Could not delete this conversation."
      );
    }
  }

  return (
    <div className="fixed bottom-5 right-5 z-[70]">
      {open && (
        <section
          aria-label="Green Path Assistant"
          className="mb-3 flex h-[min(680px,calc(100dvh-6rem))] w-[min(420px,calc(100vw-2.5rem))] flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-2xl"
        >
          <header className="flex items-center gap-2 border-b border-gray-200 bg-green-700 px-4 py-3 text-white">
            <div className="min-w-0 flex-1">
              <h2 className="font-semibold">Green Path Assistant</h2>
              <p className="truncate text-xs text-green-100">
                Marketplace guidance and your own account summaries
              </p>
            </div>
            <button
              type="button"
              disabled={sending}
              onClick={() => void startConversation()}
              title="New conversation"
              aria-label="New conversation"
              className="rounded-lg p-2 hover:bg-green-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
            >
              <Plus className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={closeAssistant}
              title="Close assistant"
              aria-label="Close assistant"
              className="rounded-lg p-2 hover:bg-green-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
            >
              <X className="h-4 w-4" />
            </button>
          </header>

          <div className="flex gap-2 border-b border-gray-100 p-3">
            <select
              aria-label="Assistant conversation"
              value={conversationId ?? ""}
              disabled={sending}
              onChange={(event) => selectConversation(event.target.value)}
              className="min-w-0 flex-1 rounded-lg border border-gray-300 bg-white px-2 py-2 text-sm text-gray-800"
            >
              <option value="">
                {loadingConversations ? "Loading conversations…" : "New conversation"}
              </option>
              {conversations.map((conversation) => (
                <option key={conversation.id} value={conversation.id}>
                  {conversation.title}
                </option>
              ))}
            </select>
            {conversationId && (
              <button
                type="button"
                disabled={sending}
                onClick={() => void deleteConversation()}
                aria-label="Delete this conversation"
                title="Delete this conversation"
                className="rounded-lg border border-gray-300 px-2 text-sm text-gray-600 hover:bg-red-50 hover:text-red-700"
              >
                Delete
              </button>
            )}
            <select
              aria-label="Reply language"
              value={language}
              onChange={(event) => {
                const selected = LANGUAGES.find(
                  (item) => item.value === event.target.value
                );
                if (selected) setLanguage(selected.value);
              }}
              className="w-32 rounded-lg border border-gray-300 bg-white px-2 py-2 text-sm text-gray-800"
            >
              {LANGUAGES.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </div>

          <div
            aria-live="polite"
            className="flex-1 space-y-3 overflow-y-auto bg-gray-50 p-4"
          >
            {loadingMessages && (
              <p className="text-center text-sm text-gray-500">Loading messages…</p>
            )}
            {!loadingMessages && messages.length === 0 && (
              <div className="rounded-xl border border-green-100 bg-white p-4 text-sm leading-6 text-gray-600">
                <p className="font-medium text-gray-900">
                  Ask about marketplace listings, your recent orders, or your own wallet.
                </p>
                <p className="mt-2">
                  Replies are processed by the configured AI provider. Avoid sharing
                  passwords, one-time codes, or bank details. Language and voice
                  quality may vary; verify important details.
                </p>
              </div>
            )}
            {messages.map((message) => (
              <div
                key={message.id}
                className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[88%] whitespace-pre-wrap break-words rounded-2xl px-3 py-2 text-sm leading-6 ${
                    message.role === "user"
                      ? "bg-green-700 text-white"
                      : "border border-gray-200 bg-white text-gray-800"
                  }`}
                >
                  {message.content}
                  {message.role === "assistant" && (
                    <button
                      type="button"
                      onClick={() => speakMessage(message.content)}
                      aria-label="Read reply aloud"
                      title="Read reply aloud"
                      className="mt-1 flex items-center gap-1 text-xs text-green-800 hover:underline"
                    >
                      <Volume2 className="h-3.5 w-3.5" />
                      Read aloud
                    </button>
                  )}
                </div>
              </div>
            ))}
            {sending && (
              <p className="text-sm text-gray-500" role="status">
                Assistant is replying…
              </p>
            )}
            <div ref={messagesEndRef} />
          </div>

          {(error || voiceNotice || recording || transcribing) && (
            <div className="space-y-1 border-t border-gray-100 px-3 py-2 text-xs">
              {error && <p role="alert" className="text-red-700">{error}</p>}
              {voiceNotice && <p className="text-gray-600">{voiceNotice}</p>}
              {recording && <p role="status" className="text-red-700">Recording… stop to review the transcript.</p>}
              {transcribing && <p role="status" className="text-gray-600">Transcribing audio…</p>}
            </div>
          )}

          <form onSubmit={(event) => void sendMessage(event)} className="border-t border-gray-200 p-3">
            <div className="flex items-end gap-2">
              <textarea
                aria-label="Message the assistant"
                value={input}
                onChange={(event) => setInput(event.target.value.slice(0, 2000))}
                onKeyDown={handleInputKeyDown}
                maxLength={2000}
                rows={2}
                placeholder="Type a message…"
                className="max-h-28 min-h-11 flex-1 resize-y rounded-xl border border-gray-300 px-3 py-2 text-sm text-gray-900 outline-none focus:border-green-600 focus:ring-2 focus:ring-green-100"
              />
              <button
                type="button"
                disabled={sending || transcribing}
                onClick={() => {
                  if (recording) recorderRef.current?.stop();
                  else void startRecording();
                }}
                aria-label={recording ? "Stop recording" : "Record a voice message"}
                title={recording ? "Stop recording" : "Record a voice message"}
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-gray-300 text-gray-700 hover:bg-gray-100 disabled:opacity-50"
              >
                {recording ? <Square className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
              </button>
              <button
                type="submit"
                disabled={!input.trim() || sending || transcribing}
                aria-label="Send message"
                title="Send message"
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-green-700 text-white hover:bg-green-800 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Send className="h-4 w-4" />
              </button>
            </div>
            <p className="mt-1 text-[11px] text-gray-500">
              Voice recognition and playback depend on provider and browser language support. Check transcripts before sending.
            </p>
          </form>
        </section>
      )}

      <button
        type="button"
        onClick={() => (open ? closeAssistant() : setOpen(true))}
        aria-label={open ? "Close Green Path Assistant" : "Open Green Path Assistant"}
        aria-expanded={open}
        className="ml-auto flex h-14 w-14 items-center justify-center rounded-full bg-green-700 text-white shadow-lg transition hover:bg-green-800 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-green-300"
      >
        {open ? <X className="h-6 w-6" /> : <MessageCircle className="h-6 w-6" />}
      </button>
    </div>
  );
}
