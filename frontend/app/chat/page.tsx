"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  Mic,
  MessageSquare,
  Plus,
  Search,
  Send,
  Square,
  UserRound,
  Wifi,
  WifiOff,
  X,
} from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { FinanciallyVerifiedBadge } from "@/components/users/FinanciallyVerifiedBadge";
import {
  Avatar,
  Button,
  Card,
  EmptyState,
  ErrorBanner,
  Field,
  Input,
  PageLoader,
  Spinner,
  StatusPill,
  Textarea,
} from "@/components/ui";
import { WS_BASE, chatApi, getAccessToken } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/context";
import { formatDateTime, formatTime, dayKey, dayLabel, shortRelative } from "@/lib/format";
import type { ChatChannel, Message, StaffRecipient } from "@/lib/types";

type SocketState = "connecting" | "live" | "polling";

/**
 * Reconnect with capped exponential backoff. The socket is a latency
 * enhancement only - the REST reads below keep the UI correct whenever it is
 * unavailable, so a failed upgrade degrades to polling instead of erroring.
 */
const RECONNECT_DELAYS = [1000, 2000, 4000, 8000, 15000];

export default function ChatPage() {
  // `useSearchParams` opts the subtree out of static prerendering, so the view
  // is wrapped in a Suspense boundary to keep the build working.
  return (
    <Suspense fallback={<div className="min-h-screen bg-gray-50" />}>
      <ChatView />
    </Suspense>
  );
}

function ChatView() {
  const { user, isLoading: authLoading } = useAuth();
  // The order rows and listing pages deep-link with `?channel=<id>`.
  const searchParams = useSearchParams();
  const requestedChannel = searchParams.get("channel");

  const [channels, setChannels] = useState<ChatChannel[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [error, setError] = useState("");
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [recording, setRecording] = useState(false);
  const [voiceBlob, setVoiceBlob] = useState<Blob | null>(null);
  const [voicePreviewUrl, setVoicePreviewUrl] = useState("");
  const [voiceUploading, setVoiceUploading] = useState(false);
  const [voiceQueue, setVoiceQueue] = useState<Message[]>([]);
  const [moderationReasons, setModerationReasons] = useState<Record<string, string>>({});
  const [moderationBusyId, setModerationBusyId] = useState("");
  const [audioUrls, setAudioUrls] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState("");
  const [query, setQuery] = useState("");
  const [socket, setSocket] = useState<SocketState>("connecting");
  const [peerTyping, setPeerTyping] = useState(false);
  const [recipientPickerOpen, setRecipientPickerOpen] = useState(false);
  const [recipients, setRecipients] = useState<StaffRecipient[]>([]);
  const [recipientSearch, setRecipientSearch] = useState("");
  const [loadingRecipients, setLoadingRecipients] = useState(false);
  const [openingRecipientId, setOpeningRecipientId] = useState("");

  const socketRef = useRef<WebSocket | null>(null);
  const pendingDraftRef = useRef("");
  const recorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const recordingChunksRef = useRef<Blob[]>([]);
  const cancelledRecordingRef = useRef(false);
  const audioUrlsRef = useRef<Record<string, string>>({});
  const voicePreviewRef = useRef("");
  const retriesRef = useRef(0);
  const typingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const loadChannels = useCallback(async () => {
    setError("");
    try {
      const res = await chatApi.channels();
      setChannels(res.results);
      // Honour a `?channel=<id>` deep link, but only if the user really is a
      // participant in it - the endpoint only ever returns their own channels.
      setActiveId((prev) => {
        if (prev) return prev;
        if (requestedChannel && res.results.some((c) => c.id === requestedChannel))
          return requestedChannel;
        return res.results[0]?.id ?? null;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load conversations.");
    } finally {
      setLoading(false);
    }
  }, [requestedChannel]);

  const loadVoiceQueue = useCallback(async () => {
    try {
      const response = await chatApi.pendingVoiceMessages();
      setVoiceQueue(response.results);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load voice reviews.");
    }
  }, []);

  useEffect(() => {
    if (!user) return;
    void loadChannels();
  }, [user, loadChannels]);

  useEffect(() => {
    if (
      user?.role === "USER_ADMIN" ||
      user?.role === "FINANCIAL_MANAGER" ||
      user?.role === "SUPER_ADMIN"
    ) {
      void loadVoiceQueue();
    }
  }, [user, loadVoiceQueue]);

  const loadMessages = useCallback(async (id: string) => {
    setError("");
    try {
      const res = await chatApi.messages(id);
      setMessages(res.results);
      await chatApi.markChannelRead(id).catch(() => undefined);
      setChannels((prev) => prev.map((c) => (c.id === id ? { ...c, unread_count: 0 } : c)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load messages.");
    } finally {
      setLoadingMessages(false);
    }
  }, []);

  useEffect(() => {
    if (!activeId) return;
    setLoadingMessages(true);
    setMessages([]);
    void loadMessages(activeId);
  }, [activeId, loadMessages]);

  // Poll while the socket is not live, and always re-read on an interval so
  // messages sent from another browser still appear.
  useEffect(() => {
    if (!activeId || !user) return;
    const interval = setInterval(
      () => {
        if (socketRef.current?.readyState === WebSocket.OPEN) return;
        void loadMessages(activeId);
      },
      6000
    );
    return () => clearInterval(interval);
  }, [activeId, user, loadMessages]);

  useEffect(() => {
    if (!activeId) return;
    const me = user;
    if (!me) return;
    const myId = me.id;
    const myName = me.full_name;
    const channelId: string = activeId;
    const token = getAccessToken();
    if (!token) return;

    let disposed = false;

    function open(id: string, jwt: string) {
      if (disposed) return;
      setSocket((s) => (s === "live" ? s : "connecting"));
      const url = `${WS_BASE}chat/${id}/?token=${encodeURIComponent(jwt)}`;
      let ws: WebSocket;
      try {
        ws = new WebSocket(url);
      } catch {
        setSocket("polling");
        return;
      }
      socketRef.current = ws;

      ws.onopen = () => {
        if (disposed) return;
        retriesRef.current = 0;
        setSocket("live");
      };

      ws.onmessage = (evt) => {
        if (disposed) return;
        let data: {
          type?: string;
          message?: Message;
          user?: string;
          is_typing?: boolean;
          error?: string;
        };
        try {
          data = JSON.parse(evt.data as string);
        } catch {
          return;
        }
        if (data.type === "chat.message" && data.message) {
          if (data.message.sender === myId) pendingDraftRef.current = "";
          setMessages((prev) =>
            prev.some((m) => m.id === data.message!.id) ? prev : [...prev, data.message!]
          );
          bottomRef.current?.scrollIntoView({ block: "end" });
          if (data.message.sender !== myId) {
            void chatApi.markChannelRead(id).catch(() => undefined);
          }
        } else if (data.type === "chat.typing") {
          setPeerTyping(Boolean(data.is_typing) && data.user !== myName);
        } else if (data.type === "chat.error") {
          setError(data.error || "Message could not be sent.");
          if (pendingDraftRef.current) {
            setDraft(pendingDraftRef.current);
            pendingDraftRef.current = "";
          }
        }
      };

      ws.onerror = () => {
        setSocket("polling");
      };

      ws.onclose = () => {
        socketRef.current = null;
        if (disposed) return;
        setSocket("polling");
        if (retriesRef.current >= RECONNECT_DELAYS.length) return;
        const delay = RECONNECT_DELAYS[retriesRef.current];
        retriesRef.current += 1;
        reconnectTimerRef.current = setTimeout(() => open(id, jwt), delay);
      };
    }

    open(channelId, token);

    return () => {
      disposed = true;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      const ws = socketRef.current;
      socketRef.current = null;
      if (ws) {
        ws.onclose = null;
        ws.close();
      }
    };
  }, [activeId, user]);

  useEffect(
    () => () => {
      if (typingTimerRef.current) clearTimeout(typingTimerRef.current);
      Object.values(audioUrlsRef.current).forEach((url) => URL.revokeObjectURL(url));
      if (voicePreviewRef.current) URL.revokeObjectURL(voicePreviewRef.current);
      mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    },
    []
  );

  const active = useMemo(
    () => channels.find((c) => c.id === activeId) ?? null,
    [channels, activeId]
  );

  const peer = useMemo(() => {
    if (!active) return null;
    return active.participants.find((p) => p.id !== user?.id) ?? active.participants[0] ?? null;
  }, [active, user]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return channels;
    return channels.filter((c) => {
      if (c.related_product_title?.toLowerCase().includes(q)) return true;
      return c.participants.some(
        (p) =>
          p.full_name.toLowerCase().includes(q) ||
          p.role_display.toLowerCase().includes(q)
      );
    });
  }, [channels, query]);

  const visibleRecipients = useMemo(() => {
    const term = recipientSearch.trim().toLowerCase();
    if (!term) return recipients;
    return recipients.filter((recipient) =>
      [recipient.full_name, recipient.role_display, recipient.scope]
        .join(" ")
        .toLowerCase()
        .includes(term)
    );
  }, [recipients, recipientSearch]);

  const isStaff =
    user?.role === "USER_ADMIN" ||
    user?.role === "FINANCIAL_MANAGER" ||
    user?.role === "SUPER_ADMIN";

  async function openRecipientPicker() {
    setRecipientPickerOpen(true);
    setRecipientSearch("");
    setLoadingRecipients(true);
    setError("");
    try {
      const response = await chatApi.staffRecipients();
      setRecipients(response.results);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load eligible staff.");
      setRecipientPickerOpen(false);
    } finally {
      setLoadingRecipients(false);
    }
  }

  async function openStaffConversation(recipient: StaffRecipient) {
    setOpeningRecipientId(recipient.id);
    setError("");
    try {
      const response = await chatApi.openChannel(recipient.id);
      const channel = response.channel;
      setChannels((previous) =>
        previous.some((item) => item.id === channel.id)
          ? previous
          : [channel, ...previous]
      );
      setActiveId(channel.id);
      setMessages([]);
      setLoadingMessages(true);
      setRecipientPickerOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not open this conversation.");
    } finally {
      setOpeningRecipientId("");
    }
  }

  function notifyTyping() {
    const ws = socketRef.current;
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ action: "typing", is_typing: true }));
    }
    if (typingTimerRef.current) clearTimeout(typingTimerRef.current);
    typingTimerRef.current = setTimeout(() => {
      const s = socketRef.current;
      if (s?.readyState === WebSocket.OPEN)
        s.send(JSON.stringify({ action: "typing", is_typing: false }));
    }, 1500);
  }

  async function send() {
    const text = draft.trim();
    if (!text || !activeId) return;
    setDraft("");
    setSending(true);
    setError("");
    setNotice("");

    const ws = socketRef.current;
    try {
      if (ws?.readyState === WebSocket.OPEN) {
        pendingDraftRef.current = text;
        ws.send(JSON.stringify({ action: "message", content: text }));
      } else {
        const response = await chatApi.sendMessage(activeId, text);
        setMessages((previous) =>
          previous.some((message) => message.id === response.message.id)
            ? previous
            : [...previous, response.message]
        );
      }
      bottomRef.current?.scrollIntoView({ block: "end" });
      if (typingTimerRef.current) clearTimeout(typingTimerRef.current);
      const socket = socketRef.current;
      if (socket?.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ action: "typing", is_typing: false }));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Message could not be sent.");
      setDraft(text);
    } finally {
      setSending(false);
    }
  }

  async function startVoiceRecording() {
    setError("");
    setNotice("");
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setError("Voice recording is not supported by this browser.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;
      const preferredType = [
        "audio/webm;codecs=opus",
        "audio/ogg;codecs=opus",
        "audio/mp4",
      ].find((type) => MediaRecorder.isTypeSupported(type));
      const recorder = preferredType
        ? new MediaRecorder(stream, { mimeType: preferredType })
        : new MediaRecorder(stream);
      recorderRef.current = recorder;
      recordingChunksRef.current = [];
      cancelledRecordingRef.current = false;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) recordingChunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
        mediaStreamRef.current = null;
        if (!cancelledRecordingRef.current) {
          const blob = new Blob(recordingChunksRef.current, {
            type: recorder.mimeType || "audio/webm",
          });
          const previewUrl = URL.createObjectURL(blob);
          voicePreviewRef.current = previewUrl;
          setVoiceBlob(blob);
          setVoicePreviewUrl(previewUrl);
        }
        cancelledRecordingRef.current = false;
      };
      recorder.start();
      setRecording(true);
    } catch (err) {
      const permissionDenied =
        err instanceof DOMException &&
        (err.name === "NotAllowedError" || err.name === "PermissionDeniedError");
      setError(
        permissionDenied
          ? "Microphone access was denied. Allow microphone access to record a voice message."
          : "Could not start recording. Check the microphone and try again."
      );
      mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }
  }

  function stopVoiceRecording() {
    if (recorderRef.current?.state === "recording") {
      recorderRef.current.stop();
      setRecording(false);
    }
  }

  function cancelVoiceRecording() {
    cancelledRecordingRef.current = true;
    if (recorderRef.current?.state === "recording") {
      recorderRef.current.stop();
    } else {
      mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }
    setRecording(false);
    setVoiceBlob(null);
    if (voicePreviewUrl) URL.revokeObjectURL(voicePreviewUrl);
    voicePreviewRef.current = "";
    setVoicePreviewUrl("");
  }

  async function sendVoiceMessage() {
    if (!activeId || !voiceBlob) return;
    if (voiceBlob.size > 10 * 1024 * 1024) {
      setError("Voice messages must be 10 MB or smaller.");
      return;
    }
    const type = voiceBlob.type || "audio/webm";
    const extension = type.includes("ogg")
      ? "ogg"
      : type.includes("mp4")
        ? "mp4"
        : type.includes("mpeg")
          ? "mp3"
          : type.includes("wav")
            ? "wav"
            : "webm";
    const file = new File([voiceBlob], `voice-message.${extension}`, { type });
    setVoiceUploading(true);
    setError("");
    setNotice("");
    try {
      const response = await chatApi.sendVoice(activeId, file);
      setMessages((previous) =>
        previous.some((message) => message.id === response.message.id)
          ? previous
          : [...previous, response.message]
      );
      setNotice(
        response.message.moderation_status === "PENDING_REVIEW"
          ? "Voice message is held for moderation and has not been sent to the recipient yet."
          : "Voice message sent."
      );
      setVoiceBlob(null);
      if (voicePreviewUrl) URL.revokeObjectURL(voicePreviewUrl);
      voicePreviewRef.current = "";
      setVoicePreviewUrl("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Voice message could not be sent.");
    } finally {
      setVoiceUploading(false);
    }
  }

  async function loadVoiceAudio(message: Message) {
    if (audioUrlsRef.current[message.id]) return;
    try {
      const blob = await chatApi.downloadVoice(message.channel, message.id);
      const url = URL.createObjectURL(blob);
      audioUrlsRef.current[message.id] = url;
      setAudioUrls((previous) => ({ ...previous, [message.id]: url }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Voice playback failed.");
    }
  }

  async function reviewVoice(message: Message, decision: "APPROVE" | "BLOCK") {
    const reason = moderationReasons[message.id]?.trim();
    if (!reason) {
      setError("Add a review reason before deciding on this voice message.");
      return;
    }
    setError("");
    setNotice("");
    setModerationBusyId(message.id);
    try {
      await chatApi.reviewVoice(message.id, decision, reason);
      setVoiceQueue((previous) => previous.filter((item) => item.id !== message.id));
      setNotice(
        decision === "APPROVE"
          ? "Voice message approved and delivered."
          : "Voice message blocked and removed from private storage."
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Voice review failed.");
    } finally {
      setModerationBusyId("");
    }
  }

  if (authLoading || loading) {
    return (
      <AppShell title="Chat" allow={["FARMER", "WHOLESALER", "RETAILER", "USER_ADMIN", "FINANCIAL_MANAGER", "SUPER_ADMIN"]}>
        <PageLoader />
      </AppShell>
    );
  }

  return (
    <AppShell
      title="Chat"
      allow={["FARMER", "WHOLESALER", "RETAILER", "USER_ADMIN", "FINANCIAL_MANAGER", "SUPER_ADMIN"]}
    >
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-gray-900">Messages</h2>
          <p className="mt-1 text-sm text-gray-500">
            {isStaff
              ? "Contact staff members available within your administrative permissions."
              : "Negotiations are tied to a listing or order and stay on the record."}
          </p>
        </div>
        <div className="flex items-center gap-3">
        {isStaff && (
          <Button
            type="button"
            icon={<Plus className="h-4 w-4" />}
            onClick={() => void openRecipientPicker()}
          >
            New Chat
          </Button>
        )}
        <span
          className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium ${
            socket === "live"
              ? "bg-green-50 text-green-700"
              : socket === "connecting"
                ? "bg-amber-50 text-amber-700"
                : "bg-gray-100 text-gray-600"
          }`}
          title={
            socket === "live"
              ? "WebSocket connected"
              : socket === "connecting"
                ? "Opening WebSocket"
                : "WebSocket unavailable - polling every 6 seconds"
          }
        >
          {socket === "live" ? (
            <Wifi className="h-3.5 w-3.5" />
          ) : (
            <WifiOff className="h-3.5 w-3.5" />
          )}
          {socket === "live" ? "Live" : socket === "connecting" ? "Connecting" : "Polling"}
        </span>
        </div>
      </div>

      {error && (
        <div className="mb-5">
          <ErrorBanner message={error} onRetry={() => void loadChannels()} />
        </div>
      )}
      {notice && (
        <div role="status" className="mb-5 rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">
          {notice}
        </div>
      )}

      {recipientPickerOpen && (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-gray-950/40 p-0 sm:items-center sm:p-4"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setRecipientPickerOpen(false);
          }}
        >
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="staff-recipient-title"
            className="max-h-[85vh] w-full max-w-lg overflow-hidden rounded-t-2xl bg-white shadow-xl sm:rounded-2xl"
          >
            <div className="flex items-center justify-between border-b border-gray-100 px-5 py-4">
              <div>
                <h2 id="staff-recipient-title" className="font-semibold text-gray-900">
                  Start a staff conversation
                </h2>
                <p className="mt-1 text-xs text-gray-500">
                  Only staff you are authorized to contact are shown.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setRecipientPickerOpen(false)}
                aria-label="Close recipient selection"
                className="rounded-lg p-2 text-gray-500 hover:bg-gray-100"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="border-b border-gray-100 p-4">
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
                <Input
                  aria-label="Search eligible staff"
                  value={recipientSearch}
                  onChange={(event) => setRecipientSearch(event.target.value)}
                  placeholder="Search staff or administrative scope"
                  className="pl-9"
                />
              </div>
            </div>
            <ul className="max-h-[55vh] divide-y divide-gray-100 overflow-y-auto">
              {loadingRecipients ? (
                <li className="flex items-center justify-center gap-2 px-5 py-10 text-sm text-gray-500">
                  <Spinner className="h-4 w-4" />
                  Loading eligible staff...
                </li>
              ) : visibleRecipients.length ? (
                visibleRecipients.map((recipient) => (
                  <li key={recipient.id}>
                    <button
                      type="button"
                      disabled={Boolean(openingRecipientId)}
                      onClick={() => void openStaffConversation(recipient)}
                      className="flex w-full items-center gap-3 px-5 py-4 text-left hover:bg-gray-50 disabled:opacity-60"
                    >
                      <span className="flex h-10 w-10 items-center justify-center rounded-full bg-green-50 text-green-700">
                        <UserRound className="h-5 w-5" />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-semibold text-gray-900">
                          {recipient.full_name}
                        </span>
                        <span className="mt-0.5 block truncate text-xs text-gray-500">
                          {recipient.role_display} · {recipient.scope || recipient.location || "Platform"}
                        </span>
                      </span>
                      {openingRecipientId === recipient.id && <Spinner className="h-4 w-4" />}
                    </button>
                  </li>
                ))
              ) : (
                <li className="px-5 py-10 text-center text-sm text-gray-500">
                  {recipients.length
                    ? "No eligible staff match your search."
                    : "There are no active staff members available to contact."}
                </li>
              )}
            </ul>
          </section>
        </div>
      )}

      {voiceQueue.length > 0 && (
        <Card className="mb-6">
          <div className="border-b border-gray-100 p-5">
            <h2 className="font-semibold text-gray-900">
              Voice messages awaiting moderation ({voiceQueue.length})
            </h2>
            <p className="mt-1 text-sm text-gray-500">
              Messages stay private to the sender until reviewed. Listen before deciding.
            </p>
          </div>
          <div className="divide-y divide-gray-100">
            {voiceQueue.map((message) => (
              <div key={message.id} className="space-y-3 p-5">
                <p className="text-sm font-medium text-gray-800">
                  From {message.sender_name} · {formatDateTime(message.sent_at)}
                </p>
                {audioUrls[message.id] ? (
                  <audio controls src={audioUrls[message.id]} className="w-full max-w-md">
                    Your browser does not support audio playback.
                  </audio>
                ) : (
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => void loadVoiceAudio(message)}
                  >
                    Load private voice recording
                  </Button>
                )}
                <Field label="Review reason" htmlFor={`voice-review-${message.id}`}>
                  <Input
                    id={`voice-review-${message.id}`}
                    value={moderationReasons[message.id] || ""}
                    onChange={(event) =>
                      setModerationReasons((previous) => ({
                        ...previous,
                        [message.id]: event.target.value,
                      }))
                    }
                    placeholder="Record why you approved or blocked this message"
                  />
                </Field>
                <div className="flex flex-wrap gap-2">
                  <Button
                    loading={moderationBusyId === message.id}
                    disabled={!moderationReasons[message.id]?.trim()}
                    onClick={() => void reviewVoice(message, "APPROVE")}
                  >
                    Approve and deliver
                  </Button>
                  <Button
                    variant="danger"
                    loading={moderationBusyId === message.id}
                    disabled={!moderationReasons[message.id]?.trim()}
                    onClick={() => void reviewVoice(message, "BLOCK")}
                  >
                    Block and delete audio
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {channels.length === 0 ? (
        <Card>
          <EmptyState
            title="No conversations yet"
            description={
              isStaff
                ? "Start a staff conversation, or open a buyer-seller conversation from a listing or order."
                : "Start one from a listing detail page or an order row."
            }
            icon={<MessageSquare className="h-8 w-8" />}
          />
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[320px_1fr]">
          <Card className="overflow-hidden">
            <div className="border-b border-gray-100 p-3">
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search people or listings"
                  className="w-full rounded-lg border border-gray-200 py-2 pl-9 pr-3 text-sm outline-none focus:border-green-500 focus:ring-1 focus:ring-green-500"
                />
              </div>
            </div>
            <ul className="max-h-[32rem] divide-y divide-gray-100 overflow-y-auto">
              {visible.length === 0 && (
                <li className="px-4 py-8 text-center text-sm text-gray-500">
                  Nothing matches &quot;{query}&quot;.
                </li>
              )}
              {visible.map((c) => {
                const other =
                  c.participants.find((p) => p.id !== user?.id) ?? c.participants[0];
                return (
                  <li key={c.id}>
                    <button
                      onClick={() => setActiveId(c.id)}
                      className={`flex w-full items-start gap-3 px-4 py-3 text-left transition ${
                        c.id === activeId ? "bg-green-50/70" : "hover:bg-gray-50"
                      }`}
                    >
                      <Avatar name={other?.full_name ?? "?"} size="sm" src={other?.profile_photo} />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-2">
                          <span className="truncate text-sm font-semibold text-gray-900">
                            {other?.full_name ?? "Conversation"}
                          </span>
                          {other?.financially_verified && <FinanciallyVerifiedBadge />}
                          {c.unread_count > 0 && (
                            <span className="shrink-0 rounded-full bg-green-600 px-1.5 py-0.5 text-[10px] font-semibold text-white">
                              {c.unread_count}
                            </span>
                          )}
                        </div>
                        {c.related_product_title && (
                          <p className="mt-0.5 truncate text-[11px] font-medium text-green-700">
                            {c.related_product_title}
                          </p>
                        )}
                        <p className="mt-0.5 truncate text-xs text-gray-500">
                          {c.last_message ? (
                            <>
                              {c.last_message.sender_name}
                              {c.last_message.sender_financially_verified && (
                                <FinanciallyVerifiedBadge />
                              )}
                              {`: ${c.last_message.content}`}
                            </>
                          ) : "No messages yet"}
                        </p>
                        {c.last_message_at && (
                          <p className="mt-0.5 text-[11px] text-gray-400">
                            {shortRelative(c.last_message_at)}
                          </p>
                        )}
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          </Card>

          <Card className="flex min-h-[32rem] flex-col overflow-hidden">
            {!active ? (
              <EmptyState
                title="Select a conversation"
                description="Pick someone on the left to read the history."
                icon={<MessageSquare className="h-8 w-8" />}
              />
            ) : (
              <>
                <div className="flex items-center justify-between gap-3 border-b border-gray-100 px-5 py-3.5">
                  <div className="flex min-w-0 items-center gap-3">
                    <Avatar name={peer?.full_name ?? "?"} size="sm" src={peer?.profile_photo} />
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-gray-900">
                        {peer?.full_name ?? "Conversation"}
                        {peer?.financially_verified && <FinanciallyVerifiedBadge />}
                      </p>
                      <div className="flex items-center gap-2">
                        {peer && <StatusPill value={peer.role} kind="role" />}
                      </div>
                    </div>
                  </div>
                  {active.related_product && (
                    <Link
                      href={`/products/${active.related_product}`}
                      className="hidden shrink-0 truncate rounded-lg bg-gray-100 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-200 sm:block"
                    >
                      {active.related_product_title ?? "View listing"}
                    </Link>
                  )}
                </div>

                <div className="flex-1 space-y-3 overflow-y-auto bg-gray-50/60 px-5 py-4">
                  {loadingMessages ? (
                    <div className="flex justify-center py-10">
                      <Spinner className="h-6 w-6 text-green-600" />
                    </div>
                  ) : messages.length === 0 ? (
                    <p className="py-10 text-center text-sm text-gray-500">
                      No messages yet. Say hello.
                    </p>
                  ) : (
                    messages.map((m, i) => {
                      const mine = m.sender === user?.id;
                      const showDivider =
                        i === 0 || dayKey(messages[i - 1].sent_at) !== dayKey(m.sent_at);
                      return (
                        <div key={m.id}>
                          {showDivider && (
                            <div className="my-4 flex items-center gap-3">
                              <span className="h-px flex-1 bg-gray-200" />
                              <span className="rounded-full bg-gray-100 px-3 py-0.5 text-[11px] font-medium text-gray-500">
                                {dayLabel(m.sent_at)}
                              </span>
                              <span className="h-px flex-1 bg-gray-200" />
                            </div>
                          )}
                          <div
                            className={`flex ${mine ? "justify-end" : "justify-start"}`}
                          >
                            <div
                              className={`max-w-[80%] rounded-2xl px-4 py-2.5 ${
                                mine
                                  ? "rounded-br-sm bg-green-600 text-white"
                                  : "rounded-bl-sm border border-gray-200 bg-white text-gray-800"
                              }`}
                            >
                              {!mine && (
                                <p className="mb-0.5 text-[11px] font-semibold text-gray-500">
                                  {m.sender_name}
                                  {m.sender_financially_verified && (
                                    <FinanciallyVerifiedBadge />
                                  )}
                                </p>
                              )}
                              {m.kind === "VOICE" ? (
                                <div className="space-y-2">
                                  {audioUrls[m.id] ? (
                                    <audio
                                      controls
                                      src={audioUrls[m.id]}
                                      className="max-w-full"
                                    >
                                      Your browser does not support audio playback.
                                    </audio>
                                  ) : m.audio_url ? (
                                    <Button
                                      type="button"
                                      variant="secondary"
                                      onClick={() => void loadVoiceAudio(m)}
                                    >
                                      Play voice message
                                    </Button>
                                  ) : (
                                    <p className="text-sm">Voice message unavailable</p>
                                  )}
                                  {m.moderation_status === "PENDING_REVIEW" && (
                                    <p className="text-xs">
                                      Pending moderation; not delivered to the recipient.
                                    </p>
                                  )}
                                  {m.moderation_status === "BLOCKED" && (
                                    <p className="text-xs">Blocked during moderation.</p>
                                  )}
                                </div>
                              ) : (
                                <p className="whitespace-pre-wrap break-words text-sm">
                                  {m.content}
                                </p>
                              )}
                              <p
                                className={`mt-1 text-right text-[10px] ${
                                  mine ? "text-green-100" : "text-gray-400"
                                }`}
                                title={formatDateTime(m.sent_at)}
                              >
                                {formatTime(m.sent_at)}
                                {mine && m.is_read ? " - read" : ""}
                              </p>
                          </div>
                          </div>
                        </div>
                      );
                    })
                  )}
                  {peerTyping && (
                    <p className="text-xs italic text-gray-500">
                      {peer?.full_name} is typing...
                    </p>
                  )}
                  <div ref={bottomRef} />
                </div>

                <div className="border-t border-gray-100 p-3">
                  {recording && (
                    <p role="status" className="mb-2 text-sm font-medium text-red-700">
                      Recording… Speak clearly, then stop to review before sending.
                    </p>
                  )}
                  {voicePreviewUrl && (
                    <div className="mb-3 flex flex-wrap items-center gap-2">
                      <audio controls src={voicePreviewUrl}>
                        Your browser does not support audio playback.
                      </audio>
                      <Button
                        type="button"
                        variant="secondary"
                        icon={<X className="h-4 w-4" />}
                        onClick={cancelVoiceRecording}
                      >
                        Discard
                      </Button>
                    </div>
                  )}
                  <div className="flex items-end gap-2">
                    <Textarea
                      value={draft}
                      rows={2}
                      onChange={(e) => {
                        setDraft(e.target.value);
                        notifyTyping();
                      }}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                          e.preventDefault();
                          void send();
                        }
                      }}
                      placeholder="Write a message. Enter to send, Shift+Enter for a new line."
                      className="resize-none"
                    />
                    {recording ? (
                      <Button
                        type="button"
                        variant="danger"
                        icon={<Square className="h-4 w-4" />}
                        onClick={stopVoiceRecording}
                      >
                        Stop
                      </Button>
                    ) : (
                      <Button
                        type="button"
                        variant="secondary"
                        icon={<Mic className="h-4 w-4" />}
                        onClick={() => void startVoiceRecording()}
                        disabled={voiceUploading}
                      >
                        Record
                      </Button>
                    )}
                    {voiceBlob && (
                      <Button
                        type="button"
                        loading={voiceUploading}
                        onClick={() => void sendVoiceMessage()}
                      >
                        Send voice
                      </Button>
                    )}
                    <Button
                      loading={sending}
                      disabled={!draft.trim()}
                      icon={<Send className="h-4 w-4" />}
                      onClick={() => void send()}
                    >
                      Send
                    </Button>
                  </div>
                </div>
              </>
            )}
          </Card>
        </div>
      )}
    </AppShell>
  );
}
