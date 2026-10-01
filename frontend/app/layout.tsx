import type { Metadata, Viewport } from "next";
import { AuthProvider } from "@/lib/auth/context";
import "./globals.css";

export const metadata: Metadata = {
  title: "Green Path — Farm-to-Marketplace",
  description:
    "AI-integrated farm-to-marketplace connecting Ethiopian farmers, wholesalers and retailers.",
  icons: { icon: "/icon.svg" },
};

export const viewport: Viewport = {
  colorScheme: "light",
  themeColor: "#16a34a",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
