import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Hedge Insight · 분기별 공시와 투자 리서치",
  description: "펀드별 13F 포트폴리오, 공통 보유와 분기별 변화, AI 리서치 및 모의 리밸런싱 워크스페이스",
  other: {
    "codex-preview": "development",
  },
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <body className="antialiased">{children}</body>
    </html>
  );
}
