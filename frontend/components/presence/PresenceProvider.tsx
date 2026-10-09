"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { getAccessToken, WS_BASE } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/context";

type PresenceState = Record<string, boolean>;

const PresenceContext = createContext<PresenceState>({});

export function PresenceProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated, user } = useAuth();
  const [presence, setPresence] = useState<PresenceState>({});

  useEffect(() => {
    if (!isAuthenticated || !user) {
      setPresence({});
      return;
    }

    let disposed = false;
    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
    let heartbeatTimer: ReturnType<typeof setInterval> | undefined;

    const connect = () => {
      if (disposed) return;
      const token = getAccessToken();
      if (!token) return;

      socket = new WebSocket(
        `${WS_BASE}/ws/presence/?token=${encodeURIComponent(token)}`
      );
      socket.onopen = () => {
        setPresence({});
        heartbeatTimer = setInterval(() => {
          if (socket?.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ action: "heartbeat" }));
          }
        }, 25_000);
      };
      socket.onmessage = (message) => {
        let event: unknown;
        try {
          event = JSON.parse(message.data);
        } catch {
          return;
        }
        if (
          event &&
          typeof event === "object" &&
          "type" in event &&
          event.type === "presence.changed" &&
          "user_id" in event &&
          typeof event.user_id === "string" &&
          "is_online" in event &&
          typeof event.is_online === "boolean"
        ) {
          setPresence((current) => ({
            ...current,
            [event.user_id as string]: event.is_online as boolean,
          }));
        }
      };
      socket.onclose = () => {
        if (heartbeatTimer) clearInterval(heartbeatTimer);
        if (!disposed) reconnectTimer = setTimeout(connect, 2_000);
      };
      socket.onerror = () => socket?.close();
    };

    connect();
    return () => {
      disposed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (heartbeatTimer) clearInterval(heartbeatTimer);
      socket?.close();
    };
  }, [isAuthenticated, user?.id]);

  const value = useMemo(() => presence, [presence]);
  return (
    <PresenceContext.Provider value={value}>
      {children}
    </PresenceContext.Provider>
  );
}

export function OnlineStatus({
  userId,
  initiallyOnline,
}: {
  userId: string;
  initiallyOnline: boolean;
}) {
  const presence = useContext(PresenceContext);
  const online = presence[userId] ?? initiallyOnline;
  const label = online ? "Online" : "Offline";

  return (
    <span
      className="inline-flex items-center gap-1.5 text-xs text-gray-500"
      role="status"
      aria-label={label}
      title={label}
    >
      <span
        aria-hidden="true"
        className={`h-2 w-2 rounded-full ${
          online ? "bg-green-500" : "bg-gray-400"
        }`}
      />
      {label}
    </span>
  );
}
