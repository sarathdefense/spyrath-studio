import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Taaza Mart AI Assistant",
  description: "Ask about our menu, hours, and specials",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, interactive-widget=resizes-content" />
        <meta name="mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="theme-color" content="#1B5E20" />
      </head>
      <body style={{ margin: 0, padding: 0, overflowX: "hidden" }}>{children}</body>
    </html>
  );
}
