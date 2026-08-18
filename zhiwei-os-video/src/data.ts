export type ProductShot = {
  file: string;
  from: number;
  duration: number;
  origin?: string;
  zoomFrom?: number;
  zoomTo?: number;
};

export type FilmScene = {
  id: string;
  number: string;
  title: string;
  eyebrow: string;
  start: number;
  duration: number;
  accent: string;
  keywords: string[];
  voice: string;
  shots?: ProductShot[];
};

export const scenes: FilmScene[] = [
  {
    id: "opening",
    number: "01",
    title: "智能体时代的新挑战",
    eyebrow: "THE NEW CHALLENGE",
    start: 0,
    duration: 450,
    accent: "#67E8F9",
    keywords: ["记忆断层", "决策不可见", "执行不可控", "系统相互割裂"],
    voice: "01-opening.mp3",
  },
  {
    id: "positioning",
    number: "02",
    title: "统一认知基础设施",
    eyebrow: "PRODUCT POSITIONING",
    start: 450,
    duration: 510,
    accent: "#5B5CEB",
    keywords: ["记忆", "推理", "执行", "治理", "可观测"],
    voice: "02-positioning.mp3",
    shots: [
      {
        file: "home.png",
        from: 0,
        duration: 270,
        origin: "54% 38%",
        zoomFrom: 1,
        zoomTo: 1.045,
      },
      {
        file: "home.png",
        from: 255,
        duration: 255,
        origin: "78% 34%",
        zoomFrom: 1.08,
        zoomTo: 1.16,
      },
    ],
  },
  {
    id: "memory",
    number: "03",
    title: "让智能体不再遗忘",
    eyebrow: "LONG-TERM MEMORY",
    start: 960,
    duration: 690,
    accent: "#7C5CFC",
    keywords: ["情景记忆", "语义记忆", "反思记忆", "知识关联"],
    voice: "03-memory.mp3",
    shots: [
      {file: "memory-console.png", from: 0, duration: 225, origin: "60% 40%"},
      {file: "memory.png", from: 210, duration: 195, origin: "62% 36%"},
      {file: "reflection.png", from: 390, duration: 165, origin: "62% 42%"},
      {file: "graph.png", from: 540, duration: 150, origin: "66% 48%"},
    ],
  },
  {
    id: "causal",
    number: "04",
    title: "让每次决策有迹可循",
    eyebrow: "CAUSAL KERNEL",
    start: 1650,
    duration: 690,
    accent: "#0EA5E9",
    keywords: ["全链路追踪", "决策过程可见", "因果关系可解释", "运行结果可复盘"],
    voice: "04-causal.mp3",
    shots: [
      {file: "causal-kernel.png", from: 0, duration: 210, origin: "62% 40%"},
      {file: "causal-graph.png", from: 195, duration: 255, origin: "62% 52%"},
      {file: "timeline.png", from: 435, duration: 135, origin: "62% 42%"},
      {file: "observability.png", from: 555, duration: 135, origin: "62% 42%"},
    ],
  },
  {
    id: "security",
    number: "05",
    title: "让智能体在边界内行动",
    eyebrow: "RUNTIME GOVERNANCE",
    start: 2340,
    duration: 750,
    accent: "#EF4444",
    keywords: ["策略先行", "默认拒绝", "模拟运行", "全程审计"],
    voice: "05-security.mp3",
    shots: [
      {file: "runtime-control.png", from: 0, duration: 315, origin: "64% 42%"},
      {file: "runtime-admin.png", from: 300, duration: 255, origin: "64% 44%"},
      {file: "policy.png", from: 540, duration: 210, origin: "64% 42%"},
    ],
  },
  {
    id: "management",
    number: "06",
    title: "从单个智能体到组织级平台",
    eyebrow: "ENTERPRISE CONTROL PLANE",
    start: 3090,
    duration: 600,
    accent: "#10B981",
    keywords: ["组织管理", "用户与权限", "策略中心", "审计中心", "部署治理"],
    voice: "06-management.mp3",
    shots: [
      {file: "enterprise-dashboard.png", from: 0, duration: 180, origin: "66% 38%"},
      {file: "organization.png", from: 165, duration: 150, origin: "66% 42%"},
      {file: "policy.png", from: 300, duration: 120, origin: "66% 42%"},
      {file: "audit.png", from: 405, duration: 105, origin: "66% 42%"},
      {file: "deployment.png", from: 495, duration: 105, origin: "66% 42%"},
    ],
  },
  {
    id: "platform",
    number: "07",
    title: "快速接入现有业务",
    eyebrow: "OPEN PLATFORM",
    start: 3690,
    duration: 630,
    accent: "#5B5CEB",
    keywords: ["开放 API", "多语言 SDK", "模块化接入", "兼容现有业务"],
    voice: "07-platform.mp3",
    shots: [
      {file: "developer-docs.png", from: 0, duration: 270, origin: "68% 30%"},
      {
        file: "developer-docs.png",
        from: 255,
        duration: 210,
        origin: "66% 50%",
        zoomFrom: 1.03,
        zoomTo: 1.09,
      },
      {
        file: "developer-docs.png",
        from: 450,
        duration: 180,
        origin: "76% 72%",
        zoomFrom: 1.05,
        zoomTo: 1.11,
      },
    ],
  },
  {
    id: "scenarios",
    number: "08",
    title: "认知能力进入真实业务",
    eyebrow: "APPLICATION SCENARIOS",
    start: 4320,
    duration: 570,
    accent: "#8B5CF6",
    keywords: ["让知识持续沉淀", "让经验能够复用", "让智能真正服务组织"],
    voice: "08-scenarios.mp3",
  },
  {
    id: "closing",
    number: "09",
    title: "让每一个组织拥有不会遗忘的大脑",
    eyebrow: "ZHIWEI OS",
    start: 4890,
    duration: 510,
    accent: "#67E8F9",
    keywords: ["记忆", "因果", "治理", "可观测"],
    voice: "09-closing.mp3",
  },
];
