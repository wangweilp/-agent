import type { Metadata, Viewport } from "next";
import { AppLayout } from "@/components/layout/app-layout";
import { Providers } from "./providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "知维 OS — AI 认知工作台",
  description: "知维 OS (Zhiwei OS) — 长期记忆 AI 智能体操作系统",
};

// 移动端视口基础 —— 不设置此项，所有 md: 断点在真机会被浏览器按 980px 桌面宽度渲染后失效
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" className="dark">
      <head>
        {/* Pre-hydration 毒数据清洗脚本 —— 在 React 水合与任何第三方库初始化之前
            以最高优先级同步执行，清除 localStorage 中的脏字符串脏数据，
            防止后续 JSON.parse("undefined") 等异常导致整树白屏。
            纵深防御层：即使当前代码已 try-catch，也能拦截浏览器扩展注入/跨版本残留。 */}
        <script
          dangerouslySetInnerHTML={{
            __html: `
              try {
                // 在 React 水合之前，暴力清洗所有 localStorage 脏数据
                for (let i = 0; i < localStorage.length; i++) {
                  const key = localStorage.key(i);
                  if (key) {
                    const val = localStorage.getItem(key);
                    if (val === "undefined" || val === "null" || val === "NaN" || val === "[object Object]") {
                      localStorage.removeItem(key);
                      console.warn("[Zhiwei OS Kernel] 拦截并清理了被污染的本地存储键:", key);
                      // removeItem 后 localStorage.length 收缩，回退索引以避免漏检
                      i--;
                    }
                  }
                }
              } catch(e) {
                console.error("[Zhiwei OS Kernel] 本地存储清洗失败", e);
              }
            `,
          }}
        />
      </head>
      <body>
        <Providers>
          <AppLayout>{children}</AppLayout>
        </Providers>
      </body>
    </html>
  );
}
