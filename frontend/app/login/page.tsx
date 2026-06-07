"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Zap, Mail, Lock, User, Loader2, AlertCircle, Eye, EyeOff } from "lucide-react";
import { api } from "@/services/api";
import { useAuthStore } from "@/stores/auth-store";
import { cn } from "@/lib/utils";

export default function LoginPage() {
  const router = useRouter();
  const setAuth = useAuthStore((s) => s.setAuth);

  const [mode, setMode] = useState<"login" | "register">("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const isValid =
    email.trim().length >= 3 &&
    password.trim().length >= 6 &&
    (mode === "login" || name.trim().length > 0);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!isValid || loading) return;

      setLoading(true);
      setError("");

      try {
        let response;
        if (mode === "register") {
          response = await api.auth.register(
            email.trim(),
            password,
            name.trim()
          );
        } else {
          response = await api.auth.login(email.trim(), password);
        }

        setAuth(
          {
            access_token: response.access_token,
            refresh_token: response.refresh_token,
            token_type: response.token_type,
            expires_in: response.expires_in,
          },
          response.user,
          response.workspace ?? {
            id: "",
            name: "默认工作区",
            role: "owner",
          }
        );

        router.push("/dashboard");
      } catch (e: unknown) {
        const msg =
          e instanceof Error ? e.message : "操作失败，请重试";
        setError(msg);
      } finally {
        setLoading(false);
      }
    },
    [mode, email, password, name, isValid, loading, setAuth, router]
  );

  const switchMode = useCallback(() => {
    setMode((prev) => (prev === "login" ? "register" : "login"));
    setError("");
  }, []);

  return (
    <div className="min-h-screen bg-os-base flex items-center justify-center p-4">
      {/* Background grid */}
      <div className="absolute inset-0 bg-os-grid bg-os-grid opacity-30 pointer-events-none" />

      <div className="relative w-full max-w-[380px] animate-fade-in">
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-12 h-12 rounded-xl bg-os-accent/15 flex items-center justify-center mb-4 ring-1 ring-os-accent/20">
            <Zap size={22} className="text-os-accent" />
          </div>
          <h1 className="text-xl font-semibold text-os-text-high tracking-tight">
            Agent OS
          </h1>
          <p className="text-sm text-os-subtle mt-1.5">
            {mode === "login" ? "登录到你的认知工作台" : "创建你的 AI 第二大脑"}
          </p>
        </div>

        {/* Card */}
        <div className="os-card p-6">
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Name (register only) */}
            {mode === "register" && (
              <div>
                <label className="text-xs text-os-subtle mb-1.5 block">
                  昵称
                </label>
                <div className="relative">
                  <User
                    size={14}
                    className="absolute left-3 top-1/2 -translate-y-1/2 text-os-muted"
                  />
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => {
                      setName(e.target.value);
                      setError("");
                    }}
                    placeholder="你的名字"
                    autoComplete="name"
                    className="w-full h-10 pl-9 pr-3 rounded bg-os-surface border border-os-border text-sm text-os-text-high placeholder:text-os-muted focus:outline-none focus:border-os-accent/50 focus:ring-1 focus:ring-os-accent/20 transition-all"
                  />
                </div>
              </div>
            )}

            {/* Email */}
            <div>
              <label className="text-xs text-os-subtle mb-1.5 block">邮箱</label>
              <div className="relative">
                <Mail
                  size={14}
                  className="absolute left-3 top-1/2 -translate-y-1/2 text-os-muted"
                />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => {
                    setEmail(e.target.value);
                    setError("");
                  }}
                  placeholder="your@email.com"
                  autoComplete="email"
                  className="w-full h-10 pl-9 pr-3 rounded bg-os-surface border border-os-border text-sm text-os-text-high placeholder:text-os-muted focus:outline-none focus:border-os-accent/50 focus:ring-1 focus:ring-os-accent/20 transition-all"
                />
              </div>
            </div>

            {/* Password */}
            <div>
              <label className="text-xs text-os-subtle mb-1.5 block">密码</label>
              <div className="relative">
                <Lock
                  size={14}
                  className="absolute left-3 top-1/2 -translate-y-1/2 text-os-muted"
                />
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value);
                    setError("");
                  }}
                  placeholder={mode === "register" ? "至少 6 位字符" : "输入密码"}
                  autoComplete={
                    mode === "register" ? "new-password" : "current-password"
                  }
                  className="w-full h-10 pl-9 pr-10 rounded bg-os-surface border border-os-border text-sm text-os-text-high placeholder:text-os-muted focus:outline-none focus:border-os-accent/50 focus:ring-1 focus:ring-os-accent/20 transition-all"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-os-muted hover:text-os-subtle transition-colors"
                  tabIndex={-1}
                >
                  {showPassword ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
            </div>

            {/* Error */}
            {error && (
              <div className="flex items-center gap-2 text-xs text-os-danger bg-os-danger/5 rounded px-3 py-2 border border-os-danger/10">
                <AlertCircle size={13} className="shrink-0" />
                {error}
              </div>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={!isValid || loading}
              className={cn(
                "w-full h-10 rounded text-sm font-medium transition-all flex items-center justify-center gap-2",
                isValid && !loading
                  ? "bg-os-accent text-white hover:bg-os-accent/90 shadow-os-glow"
                  : "bg-os-elevated text-os-muted cursor-not-allowed"
              )}
            >
              {loading ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  {mode === "login" ? "登录中..." : "注册中..."}
                </>
              ) : mode === "login" ? (
                "登录"
              ) : (
                "注册"
              )}
            </button>
          </form>
        </div>

        {/* Toggle mode */}
        <p className="text-center text-xs text-os-subtle mt-4">
          {mode === "login" ? "还没有账号？" : "已有账号？"}
          <button
            onClick={switchMode}
            className="ml-1 text-os-accent hover:text-os-accent/80 transition-colors font-medium"
          >
            {mode === "login" ? "立即注册" : "去登录"}
          </button>
        </p>
      </div>
    </div>
  );
}
