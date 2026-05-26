import type { Metadata } from "next";
import { AppLayout } from "@/components/layout/app-layout";
import { Providers } from "./providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "Agent OS — AI 认知工作台",
  description: "长期记忆 AI Agent 操作系统",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" className="dark">
      <body>
        <Providers>
          <AppLayout>{children}</AppLayout>
        </Providers>
      </body>
    </html>
  );
}
