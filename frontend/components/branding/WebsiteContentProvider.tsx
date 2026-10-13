"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { websiteContentApi } from "@/lib/api/client";
import type { WebsiteContent } from "@/lib/types";

const DEFAULT_CONTENT: WebsiteContent = {
  platform_name: "Green Path",
  logo_url: null,
  favicon_url: null,
  hero_image_url: null,
  updated_at: null,
  updated_by: null,
  content: {
    landing_badge: "AI-integrated farm-to-marketplace",
    landing_title: "Connect Ethiopian farmers directly to wholesale buyers",
    landing_subtitle: "A trusted marketplace for every side of the agricultural trade.",
    landing_description:
      "GreenPath connects farmers, wholesalers and retailers with verified accounts, transparent transactions and secure payments.",
    landing_primary_button: "Start trading",
    landing_secondary_button: "Sign in",
    about_title: "About the platform",
    about_description: "A single audited platform for agricultural trade.",
    marketplace_title: "Built for every side of the trade",
    marketplace_description: "One platform, three commercial roles, and staff oversight.",
    farmer_description: "List your produce and manage orders.",
    wholesaler_description: "Source directly from farmers and manage bulk orders.",
    retailer_description: "Discover wholesale listings and contact suppliers.",
    feature_verified_title: "Verified accounts",
    feature_verified_description: "Commercial accounts are reviewed before trading.",
    feature_payments_title: "Verified payments",
    feature_payments_description: "Financial Managers verify transfers and resolve disputes.",
    feature_chat_title: "Real-time chat",
    feature_chat_description: "Trade conversations stay on the record.",
    feature_audit_title: "Audited staff actions",
    feature_audit_description: "Privileged actions are recorded in the audit log.",
    footer_text: "GreenPath — Farm-to-Marketplace",
    contact_email: "",
    contact_phone: "",
  },
};

interface WebsiteContentContextValue {
  website: WebsiteContent;
  loading: boolean;
  refresh: () => Promise<WebsiteContent>;
}

const WebsiteContentContext = createContext<WebsiteContentContextValue>({
  website: DEFAULT_CONTENT,
  loading: true,
  refresh: async () => DEFAULT_CONTENT,
});

export function WebsiteContentProvider({ children }: { children: ReactNode }) {
  const [website, setWebsite] = useState(DEFAULT_CONTENT);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const current = await websiteContentApi.public();
    setWebsite(current);
    return current;
  }, []);

  useEffect(() => {
    let active = true;
    websiteContentApi
      .public()
      .then((current) => {
        if (active) setWebsite(current);
      })
      .catch(() => {
        // The public site keeps its bundled defaults if content is unavailable.
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    document.title = `${website.platform_name || "Green Path"} — Farm-to-Marketplace`;
    if (!website.favicon_url) return;
    let icon = document.querySelector<HTMLLinkElement>("link[rel~='icon']");
    if (!icon) {
      icon = document.createElement("link");
      icon.rel = "icon";
      document.head.appendChild(icon);
    }
    icon.href = website.favicon_url;
  }, [website.favicon_url, website.platform_name]);

  return (
    <WebsiteContentContext.Provider value={{ website, loading, refresh }}>
      {children}
    </WebsiteContentContext.Provider>
  );
}

export function useWebsiteContent() {
  return useContext(WebsiteContentContext);
}
