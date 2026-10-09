"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { MessageSquare, Search, Send, Wifi, WifiOff } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { FinanciallyVerifiedBadge } from "@/components/users/FinanciallyVerifiedBadge";
import {
  Avatar,
  Button,
  Card,
  EmptyState,
  ErrorBanner,
  PageLoader,
  Spinner,
  StatusPill,
  Textarea,
} from "@/components/ui";
import { WS_BASE, chatApi, getAccessToken } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/context";
import { formatDateTime, formatTime, dayKey, dayLabel, shortRelative } from "@/lib/format";
import type { ChatChannel, Message } from "@/lib/types";

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
  const [query, setQuery] = useState("");
  const [socket, setSocket] = useState<SocketState>("connecting");
  const [peerTyping, setPeerTyping] = useState(false);

  const socketRef = useRef<WebSocket | null>(null);
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

  useEffect(() => {
    if (!user) return;
    void loadChannels();
  }, [user, loadChannels]);

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
        let data: { type?: string; message?: Message; user?: string; is_typing?: boolean };
        try {
          data = JSON.parse(evt.data as string);
        } catch {
          return;
        }
        if (data.type === "chat.message" && data.message) {
          setMessages((prev) =>
            prev.some((m) => m.id === data.message!.id) ? prev : [...prev, data.message!]
          );
          bottomRef.current?.scrollIntoView({ block: "end" });
          if (data.message.sender !== myId) {
            void chatApi.markChannelRead(id).catch(() => undefined);
          }
        } else if (data.type === "chat.typing") {
          setPeerTyping(Boolean(data.is_typing) && data.user !== myName);
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

    const ws = socketRef.current;
    try {
      if (ws?.readyState === WebSocket.OPEN) {
        // The consumer persists and echoes the message back to the group.
        ws.send(JSON.stringify({ action: "message", content: text }));
      } else {
        const res = await chatApi.sendMessage(activeId, text);
        setMessages((prev) =>
          prev.some((m) => m.id === res.message.id) ? prev : [...prev, res.message]
        );
      }
      bottomRef.current?.scrollIntoView({ block: "end" });
      if (typingTimerRef.current) clearTimeout(typingTimerRef.current);
      const s = socketRef.current;
      if (s?.readyState === WebSocket.OPEN)
        s.send(JSON.stringify({ action: "typing", is_typing: false }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Message could not be sent.");
      setDraft(text);
    } finally {
      setSending(false);
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
            Negotiations are tied to a listing or order and stay on the record.
          </p>
        </div>
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

      {error && (
        <div className="mb-5">
          <ErrorBanner message={error} onRetry={() => void loadChannels()} />
        </div>
      )}

      {channels.length === 0 ? (
        <Card>
          <EmptyState
            title="No conversations yet"
            description="Start one from a listing detail page or an order row."
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
                        {peer && (
                          <span className="truncate text-xs text-gray-500">
                            {peer.location || peer.phone}
                          </span>
                        )}
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
                              <p className="whitespace-pre-wrap break-words text-sm">
                                {m.content}
                              </p>
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
