import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        os: {
          base: "#09090B",
          surface: "#111113",
          elevated: "#18181B",
          border: "#27272A",
          muted: "#3F3F46",
          subtle: "#52525B",
          text: "#A1A1AA",
          "text-high": "#E4E4E7",
          accent: "#818CF8",
          "accent-soft": "rgba(129,140,248,0.12)",
          "accent-glow": "rgba(129,140,248,0.25)",
          success: "#34D399",
          warning: "#FBBF24",
          danger: "#F87171",
          // 新增：次要强调色
          "accent-violet": "#A78BFA",
          "accent-cyan": "#22D3EE",
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "PingFang SC",
          "Microsoft YaHei",
          "sans-serif",
        ],
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },
      fontSize: {
        "2xs": ["0.625rem", { lineHeight: "0.875rem" }],
      },
      spacing: {
        18: "4.5rem",
        88: "22rem",
      },
      borderRadius: {
        os: "0.625rem",
        "os-lg": "0.875rem",
      },
      boxShadow: {
        "os-sm": "0 1px 2px 0 rgba(0,0,0,0.4)",
        os: "0 1px 3px 0 rgba(0,0,0,0.5), 0 1px 2px -1px rgba(0,0,0,0.5)",
        "os-md": "0 4px 6px -1px rgba(0,0,0,0.5), 0 2px 4px -2px rgba(0,0,0,0.5)",
        "os-lg": "0 10px 15px -3px rgba(0,0,0,0.6), 0 4px 6px -4px rgba(0,0,0,0.6)",
        "os-glow": "0 0 20px rgba(129,140,248,0.08)",
        "os-glow-lg": "0 0 30px rgba(129,140,248,0.12), 0 0 60px rgba(129,140,248,0.04)",
        "os-inner": "inset 0 1px 2px rgba(255,255,255,0.02)",
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "fade-in": "fadeIn 0.3s ease-out",
        "slide-up": "slideUp 0.3s ease-out",
        "slide-right": "slideRight 0.3s ease-out",
        shimmer: "shimmer 2s linear infinite",
        "status-breathe": "statusBreathe 2s ease-in-out infinite",
        "glow-pulse": "glowPulse 4s ease-in-out infinite",
        "float": "float 6s ease-in-out infinite",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        slideRight: {
          "0%": { opacity: "0", transform: "translateX(-8px)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        statusBreathe: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.5" },
        },
        glowPulse: {
          "0%, 100%": { boxShadow: "0 0 10px rgba(129,140,248,0.04)" },
          "50%": { boxShadow: "0 0 25px rgba(129,140,248,0.1)" },
        },
        float: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-4px)" },
        },
      },
      backgroundImage: {
        "os-grid":
          "linear-gradient(rgba(255,255,255,0.02) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.02) 1px, transparent 1px)",
        "os-grid-fine":
          "linear-gradient(rgba(255,255,255,0.01) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.01) 1px, transparent 1px)",
        "os-accent-grad": "linear-gradient(135deg, rgba(129,140,248,0.15), rgba(167,139,250,0.08))",
        "os-accent-grad-hover": "linear-gradient(135deg, rgba(129,140,248,0.22), rgba(167,139,250,0.12))",
      },
      backgroundSize: {
        "os-grid": "32px 32px",
        "os-grid-fine": "16px 16px",
      },
    },
  },
  plugins: [],
} satisfies Config;
