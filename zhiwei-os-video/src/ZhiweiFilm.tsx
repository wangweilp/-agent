import {Audio} from "@remotion/media";
import {
  Activity,
  BarChart3,
  BookOpen,
  BrainCircuit,
  Code2,
  Database,
  GitBranch,
  Headphones,
  Landmark,
  Network,
  ShieldCheck,
} from "lucide-react";
import type {LucideIcon} from "lucide-react";
import {
  AbsoluteFill,
  Easing,
  Img,
  Sequence,
  interpolate,
  staticFile,
  useCurrentFrame,
} from "remotion";
import {Captions} from "./Captions";
import type {FilmScene, ProductShot} from "./data";
import {scenes} from "./data";

const clampOptions = {
  extrapolateLeft: "clamp" as const,
  extrapolateRight: "clamp" as const,
};

const GridBackdrop: React.FC<{dark?: boolean}> = ({dark = false}) => {
  return (
    <AbsoluteFill
      style={{
        backgroundColor: dark ? "#050816" : "#F7F8FC",
        backgroundImage: dark
          ? "linear-gradient(rgba(103,232,249,0.045) 1px, transparent 1px), linear-gradient(90deg, rgba(103,232,249,0.045) 1px, transparent 1px)"
          : "linear-gradient(rgba(91,92,235,0.045) 1px, transparent 1px), linear-gradient(90deg, rgba(91,92,235,0.045) 1px, transparent 1px)",
        backgroundSize: "64px 64px",
      }}
    />
  );
};

const Vignette: React.FC<{dark?: boolean}> = ({dark = false}) => {
  return (
    <AbsoluteFill
      style={{
        background: dark
          ? "radial-gradient(circle at 52% 42%, transparent 20%, rgba(2,6,23,0.18) 58%, rgba(2,6,23,0.88) 100%)"
          : "linear-gradient(180deg, rgba(255,255,255,0.03), rgba(241,245,249,0.12))",
      }}
    />
  );
};

const ScreenshotShot: React.FC<ProductShot> = ({
  file,
  duration,
  origin = "62% 42%",
  zoomFrom = 1.015,
  zoomTo = 1.07,
}) => {
  const frame = useCurrentFrame();
  const fade = 12;

  return (
    <AbsoluteFill
      style={{
        opacity: interpolate(
          frame,
          [0, fade, duration - fade, duration],
          [0, 1, 1, 0],
          {
            ...clampOptions,
            easing: Easing.bezier(0.16, 1, 0.3, 1),
          },
        ),
        overflow: "hidden",
        backgroundColor: "#F7F8FC",
      }}
    >
      <Img
        src={staticFile(`ui/${file}`)}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          transformOrigin: origin,
          scale: interpolate(frame, [0, duration], [zoomFrom, zoomTo], {
            ...clampOptions,
            easing: Easing.bezier(0.2, 0.8, 0.2, 1),
          }),
        }}
      />
      <AbsoluteFill
        style={{
          boxShadow: "inset 0 0 100px rgba(30,41,59,0.10)",
        }}
      />
    </AbsoluteFill>
  );
};

const ShotMontage: React.FC<{shots: ProductShot[]}> = ({shots}) => {
  return (
    <AbsoluteFill>
      {shots.map((shot, index) => (
        <Sequence
          key={`${shot.file}-${shot.from}`}
          from={shot.from}
          durationInFrames={shot.duration}
          name={`Shot ${index + 1}: ${shot.file}`}
        >
          <ScreenshotShot {...shot} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};

const SceneBadge: React.FC<{scene: FilmScene; dark?: boolean}> = ({
  scene,
  dark = false,
}) => {
  const frame = useCurrentFrame();

  return (
    <div
      style={{
        position: "absolute",
        top: 82,
        right: 86,
        display: "flex",
        alignItems: "center",
        gap: 18,
        padding: "14px 22px 14px 16px",
        borderRadius: 18,
        border: dark
          ? "1px solid rgba(255,255,255,0.16)"
          : "1px solid rgba(15,23,42,0.09)",
        background: dark
          ? "rgba(5,8,22,0.64)"
          : "rgba(255,255,255,0.78)",
        boxShadow: dark
          ? "0 20px 70px rgba(0,0,0,0.30)"
          : "0 18px 55px rgba(15,23,42,0.12)",
        backdropFilter: "blur(20px)",
        opacity: interpolate(frame, [8, 22], [0, 1], {
          ...clampOptions,
          easing: Easing.bezier(0.16, 1, 0.3, 1),
        }),
        translate: interpolate(frame, [8, 24], ["24px 0px", "0px 0px"], {
          ...clampOptions,
          easing: Easing.bezier(0.16, 1, 0.3, 1),
        }),
      }}
    >
      <div
        style={{
          width: 48,
          height: 48,
          borderRadius: 14,
          display: "grid",
          placeItems: "center",
          backgroundColor: scene.accent,
          color: "#FFFFFF",
          fontSize: 22,
          fontWeight: 850,
        }}
      >
        {scene.number}
      </div>
      <div>
        <div
          style={{
            color: dark ? "rgba(255,255,255,0.58)" : "#64748B",
            fontSize: 18,
            fontWeight: 750,
            letterSpacing: "0.12em",
          }}
        >
          {scene.eyebrow}
        </div>
        <div
          style={{
            marginTop: 3,
            color: dark ? "#FFFFFF" : "#0F172A",
            fontSize: 28,
            fontWeight: 780,
          }}
        >
          {scene.title}
        </div>
      </div>
    </div>
  );
};

const KeywordTicker: React.FC<{
  scene: FilmScene;
  dark?: boolean;
  truthNote?: string;
}> = ({scene, dark = false, truthNote}) => {
  const frame = useCurrentFrame();
  const activeIndex = Math.min(
    scene.keywords.length - 1,
    Math.floor((frame / scene.duration) * scene.keywords.length),
  );
  const active = scene.keywords[activeIndex];
  const segmentFrames = scene.duration / scene.keywords.length;
  const local = frame - activeIndex * segmentFrames;

  return (
    <div
      style={{
        position: "absolute",
        left: 316,
        bottom: 202,
        display: "flex",
        alignItems: "center",
        gap: 14,
      }}
    >
      <div
        style={{
          minWidth: 300,
          minHeight: 62,
          borderRadius: 18,
          border: dark
            ? "1px solid rgba(255,255,255,0.15)"
            : "1px solid rgba(15,23,42,0.10)",
          background: dark
            ? "rgba(5,8,22,0.72)"
            : "rgba(255,255,255,0.86)",
          boxShadow: "0 16px 55px rgba(15,23,42,0.14)",
          backdropFilter: "blur(18px)",
          display: "flex",
          alignItems: "center",
          padding: "0 26px",
          color: dark ? "#FFFFFF" : "#0F172A",
          fontSize: 34,
          fontWeight: 780,
          opacity: interpolate(
            local,
            [0, 8, segmentFrames - 8, segmentFrames],
            [0, 1, 1, 0],
            clampOptions,
          ),
          translate: interpolate(
            local,
            [0, 10],
            ["0px 14px", "0px 0px"],
            clampOptions,
          ),
        }}
      >
        <span
          style={{
            width: 10,
            height: 10,
            borderRadius: 999,
            marginRight: 14,
            backgroundColor: scene.accent,
            boxShadow: `0 0 20px ${scene.accent}`,
          }}
        />
        {active}
      </div>
      {truthNote ? (
        <div
          style={{
            color: dark ? "rgba(255,255,255,0.7)" : "#475569",
            fontSize: 24,
            fontWeight: 650,
            padding: "15px 20px",
            borderRadius: 16,
            background: dark
              ? "rgba(5,8,22,0.55)"
              : "rgba(255,255,255,0.74)",
            backdropFilter: "blur(16px)",
          }}
        >
          {truthNote}
        </div>
      ) : null}
    </div>
  );
};

const ProductScene: React.FC<{scene: FilmScene}> = ({scene}) => {
  if (!scene.shots) {
    return null;
  }

  return (
    <AbsoluteFill>
      <GridBackdrop />
      <ShotMontage shots={scene.shots} />
      <div
        style={{
          position: "absolute",
          left: 0,
          bottom: 0,
          width: 270,
          height: 76,
          background:
            "linear-gradient(90deg, #F7F8FC 72%, rgba(247,248,252,0))",
        }}
      />
      <SceneBadge scene={scene} />
      <KeywordTicker
        scene={scene}
        truthNote={
          scene.id === "security"
            ? "当前：安全治理控制面 · 模拟运行"
            : undefined
        }
      />
    </AbsoluteFill>
  );
};

const OpeningScene: React.FC<{scene: FilmScene}> = ({scene}) => {
  const frame = useCurrentFrame();

  return (
    <AbsoluteFill style={{backgroundColor: "#020617", overflow: "hidden"}}>
      <Img
        src={staticFile("visuals/fragmented-intelligence.png")}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          scale: interpolate(frame, [0, scene.duration], [1.03, 1.11], {
            ...clampOptions,
            easing: Easing.bezier(0.2, 0.8, 0.2, 1),
          }),
          opacity: interpolate(frame, [300, 390], [1, 0.42], clampOptions),
        }}
      />
      <Vignette dark />
      <div
        style={{
          position: "absolute",
          top: 110,
          left: 110,
          color: "rgba(255,255,255,0.56)",
          fontSize: 21,
          fontWeight: 750,
          letterSpacing: "0.18em",
          opacity: interpolate(frame, [8, 30], [0, 1], clampOptions),
        }}
      >
        AGENT ERA / NEW FAILURE MODES
      </div>
      <div
        style={{
          position: "absolute",
          top: 160,
          left: 110,
          maxWidth: 930,
          color: "#FFFFFF",
          fontSize: 76,
          lineHeight: 1.08,
          fontWeight: 850,
          letterSpacing: "-0.04em",
          opacity: interpolate(frame, [12, 38, 302, 330], [0, 1, 1, 0], {
            ...clampOptions,
            easing: Easing.bezier(0.16, 1, 0.3, 1),
          }),
          translate: interpolate(
            frame,
            [12, 42],
            ["0px 24px", "0px 0px"],
            clampOptions,
          ),
        }}
      >
        智能体时代
        <br />
        正在出现新的断层
      </div>
      {scene.keywords.map((keyword, index) => {
        const reveal = 68 + index * 55;
        const positions = [
          {left: 120, top: 470},
          {left: 540, top: 560},
          {left: 990, top: 465},
          {left: 1350, top: 590},
        ];
        const position = positions[index];
        return (
          <div
            key={keyword}
            style={{
              position: "absolute",
              ...position,
              minWidth: 290,
              padding: "20px 26px",
              borderRadius: 20,
              border: "1px solid rgba(103,232,249,0.22)",
              background:
                "linear-gradient(135deg, rgba(8,19,42,0.82), rgba(18,25,62,0.58))",
              boxShadow: "0 20px 80px rgba(0,0,0,0.28)",
              backdropFilter: "blur(18px)",
              color: "#E2E8F0",
              fontSize: 38,
              fontWeight: 730,
              opacity: interpolate(
                frame,
                [reveal, reveal + 18, 305, 330],
                [0, 1, 1, 0],
                clampOptions,
              ),
              translate: interpolate(
                frame,
                [reveal, reveal + 20],
                [`0px ${index % 2 === 0 ? 26 : -26}px`, "0px 0px"],
                clampOptions,
              ),
            }}
          >
            <span style={{color: index === 2 ? "#F59E0B" : "#67E8F9"}}>
              0{index + 1}
            </span>
            <span style={{marginLeft: 18}}>{keyword}</span>
          </div>
        );
      })}
      <div
        style={{
          position: "absolute",
          left: "50%",
          top: "48%",
          width: 270,
          height: 270,
          borderRadius: "50%",
          border: "1px solid rgba(103,232,249,0.55)",
          boxShadow:
            "0 0 80px rgba(103,232,249,0.28), inset 0 0 60px rgba(91,92,235,0.24)",
          background:
            "radial-gradient(circle, rgba(255,255,255,0.96) 0%, rgba(103,232,249,0.56) 8%, rgba(91,92,235,0.18) 28%, rgba(5,8,22,0.1) 66%)",
          opacity: interpolate(frame, [320, 370], [0, 1], clampOptions),
          scale: interpolate(frame, [320, 390], [0.55, 1], {
            ...clampOptions,
            easing: Easing.bezier(0.16, 1, 0.3, 1),
          }),
          translate: "-50% -50%",
        }}
      />
      <div
        style={{
          position: "absolute",
          left: "50%",
          top: "48%",
          translate: "-50% -50%",
          color: "#FFFFFF",
          fontSize: 74,
          fontWeight: 900,
          letterSpacing: "-0.04em",
          textShadow: "0 0 34px rgba(103,232,249,0.55)",
          opacity: interpolate(frame, [355, 405], [0, 1], clampOptions),
        }}
      >
        知维 OS
      </div>
    </AbsoluteFill>
  );
};

type ScenarioCard = {
  title: string;
  icon: LucideIcon;
  accent: string;
};

const scenarioCards: ScenarioCard[] = [
  {title: "企业知识助手", icon: BookOpen, accent: "#5B5CEB"},
  {title: "智能客服", icon: Headphones, accent: "#0EA5E9"},
  {title: "运营分析智能体", icon: BarChart3, accent: "#10B981"},
  {title: "研发协作智能体", icon: Code2, accent: "#8B5CF6"},
  {title: "组织决策辅助", icon: Landmark, accent: "#F59E0B"},
  {title: "多智能体协同", icon: Network, accent: "#EC4899"},
];

const ScenariosScene: React.FC<{scene: FilmScene}> = ({scene}) => {
  const frame = useCurrentFrame();

  return (
    <AbsoluteFill style={{backgroundColor: "#050816", overflow: "hidden"}}>
      <GridBackdrop dark />
      <Img
        src={staticFile("ui/causal-graph.png")}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          filter: "blur(14px) saturate(0.75)",
          scale: interpolate(frame, [0, scene.duration], [1.1, 1.18], {
            ...clampOptions,
            easing: Easing.bezier(0.2, 0.8, 0.2, 1),
          }),
          opacity: 0.25,
        }}
      />
      <AbsoluteFill
        style={{
          background:
            "radial-gradient(circle at 50% 45%, rgba(91,92,235,0.20), rgba(5,8,22,0.92) 72%)",
        }}
      />
      <div
        style={{
          position: "absolute",
          top: 108,
          left: 120,
          right: 120,
          display: "flex",
          alignItems: "flex-end",
          justifyContent: "space-between",
        }}
      >
        <div>
          <div
            style={{
              color: "#A5B4FC",
              fontSize: 22,
              fontWeight: 750,
              letterSpacing: "0.16em",
            }}
          >
            APPLICATION SCENARIOS
          </div>
          <div
            style={{
              marginTop: 14,
              color: "#FFFFFF",
              fontSize: 68,
              lineHeight: 1.08,
              fontWeight: 850,
              letterSpacing: "-0.035em",
            }}
          >
            认知能力
            <br />
            进入真实业务
          </div>
        </div>
        <div
          style={{
            color: "rgba(255,255,255,0.52)",
            fontSize: 28,
            lineHeight: 1.55,
            maxWidth: 560,
            textAlign: "right",
          }}
        >
          知识沉淀 · 经验复用 · 持续协同
          <br />
          从单点工具走向组织认知资产
        </div>
      </div>
      <div
        style={{
          position: "absolute",
          left: 120,
          right: 120,
          top: 388,
          display: "grid",
          gridTemplateColumns: "repeat(3, 1fr)",
          gap: 24,
        }}
      >
        {scenarioCards.map((card, index) => {
          const reveal = 55 + index * 28;
          const Icon = card.icon;
          return (
            <div
              key={card.title}
              style={{
                minHeight: 168,
                borderRadius: 24,
                border: "1px solid rgba(255,255,255,0.13)",
                background:
                  "linear-gradient(135deg, rgba(15,23,42,0.88), rgba(30,41,59,0.60))",
                boxShadow: "0 28px 80px rgba(0,0,0,0.28)",
                backdropFilter: "blur(18px)",
                display: "flex",
                alignItems: "center",
                gap: 24,
                padding: "26px 30px",
                opacity: interpolate(
                  frame,
                  [reveal, reveal + 18],
                  [0, 1],
                  clampOptions,
                ),
                translate: interpolate(
                  frame,
                  [reveal, reveal + 22],
                  ["0px 24px", "0px 0px"],
                  {
                    ...clampOptions,
                    easing: Easing.bezier(0.16, 1, 0.3, 1),
                  },
                ),
              }}
            >
              <div
                style={{
                  width: 76,
                  height: 76,
                  borderRadius: 22,
                  display: "grid",
                  placeItems: "center",
                  color: "#FFFFFF",
                  backgroundColor: card.accent,
                  boxShadow: `0 18px 42px ${card.accent}42`,
                  flex: "0 0 auto",
                }}
              >
                <Icon size={38} strokeWidth={1.8} />
              </div>
              <div
                style={{
                  color: "#FFFFFF",
                  fontSize: 32,
                  fontWeight: 760,
                  lineHeight: 1.24,
                }}
              >
                {card.title}
              </div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

const moduleLabels: Array<{
  title: string;
  icon: LucideIcon;
  color: string;
  left: number;
  top: number;
}> = [
  {title: "因果内核", icon: GitBranch, color: "#60A5FA", left: 1040, top: 185},
  {title: "记忆引擎", icon: Database, color: "#8B5CF6", left: 1490, top: 250},
  {title: "安全治理", icon: ShieldCheck, color: "#34D399", left: 1450, top: 710},
  {title: "可观测性", icon: Activity, color: "#67E8F9", left: 980, top: 770},
];

const ClosingScene: React.FC<{scene: FilmScene}> = ({scene}) => {
  const frame = useCurrentFrame();

  return (
    <AbsoluteFill style={{backgroundColor: "#020617", overflow: "hidden"}}>
      <Img
        src={staticFile("visuals/cognitive-core.png")}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          scale: interpolate(frame, [0, scene.duration], [1.02, 1.1], {
            ...clampOptions,
            easing: Easing.bezier(0.2, 0.8, 0.2, 1),
          }),
        }}
      />
      <AbsoluteFill
        style={{
          background:
            "linear-gradient(90deg, rgba(2,6,23,0.98) 0%, rgba(2,6,23,0.82) 35%, rgba(2,6,23,0.05) 68%, rgba(2,6,23,0.22) 100%)",
        }}
      />
      <div
        style={{
          position: "absolute",
          left: 118,
          top: 180,
          maxWidth: 720,
          opacity: interpolate(frame, [16, 48], [0, 1], {
            ...clampOptions,
            easing: Easing.bezier(0.16, 1, 0.3, 1),
          }),
          translate: interpolate(
            frame,
            [16, 52],
            ["0px 28px", "0px 0px"],
            {
              ...clampOptions,
              easing: Easing.bezier(0.16, 1, 0.3, 1),
            },
          ),
        }}
      >
        <div
          style={{
            color: "#67E8F9",
            fontSize: 22,
            fontWeight: 760,
            letterSpacing: "0.18em",
          }}
        >
          ZHIWEI OS / COGNITIVE RUNTIME
        </div>
        <div
          style={{
            marginTop: 24,
            color: "#FFFFFF",
            fontSize: 112,
            fontWeight: 900,
            lineHeight: 1,
            letterSpacing: "-0.055em",
          }}
        >
          知维 <span style={{color: "#818CF8"}}>OS</span>
        </div>
        <div
          style={{
            marginTop: 28,
            color: "#CBD5E1",
            fontSize: 40,
            lineHeight: 1.5,
            fontWeight: 620,
          }}
        >
          AI 认知操作系统与智能体开放平台
        </div>
        <div
          style={{
            marginTop: 34,
            width: 96,
            height: 4,
            borderRadius: 99,
            background: "linear-gradient(90deg, #67E8F9, #818CF8)",
          }}
        />
        <div
          style={{
            marginTop: 34,
            color: "#FFFFFF",
            fontSize: 52,
            lineHeight: 1.35,
            fontWeight: 820,
            letterSpacing: "-0.025em",
          }}
        >
          让每一个组织
          <br />
          拥有不会遗忘的大脑
        </div>
      </div>
      {moduleLabels.map((module, index) => {
        const Icon = module.icon;
        const reveal = 80 + index * 42;
        return (
          <div
            key={module.title}
            style={{
              position: "absolute",
              left: module.left,
              top: module.top,
              display: "flex",
              alignItems: "center",
              gap: 13,
              color: "#FFFFFF",
              fontSize: 27,
              fontWeight: 720,
              padding: "13px 18px",
              borderRadius: 18,
              border: `1px solid ${module.color}55`,
              background: "rgba(5,8,22,0.66)",
              boxShadow: `0 0 36px ${module.color}24`,
              backdropFilter: "blur(14px)",
              opacity: interpolate(
                frame,
                [reveal, reveal + 20],
                [0, 1],
                clampOptions,
              ),
              scale: interpolate(
                frame,
                [reveal, reveal + 24],
                [0.86, 1],
                {
                  ...clampOptions,
                  easing: Easing.bezier(0.16, 1, 0.3, 1),
                },
              ),
            }}
          >
            <Icon size={30} color={module.color} />
            {module.title}
          </div>
        );
      })}
      <div
        style={{
          position: "absolute",
          right: 86,
          bottom: 48,
          color: "rgba(255,255,255,0.52)",
          fontSize: 20,
          letterSpacing: "0.08em",
          opacity: interpolate(frame, [300, 340], [0, 1], clampOptions),
        }}
      >
        官方网站 · 产品演示 · 开放平台
      </div>
    </AbsoluteFill>
  );
};

const SceneContent: React.FC<{scene: FilmScene}> = ({scene}) => {
  if (scene.id === "opening") {
    return <OpeningScene scene={scene} />;
  }
  if (scene.id === "scenarios") {
    return <ScenariosScene scene={scene} />;
  }
  if (scene.id === "closing") {
    return <ClosingScene scene={scene} />;
  }
  return <ProductScene scene={scene} />;
};

const BoundaryFlashes: React.FC = () => {
  const frame = useCurrentFrame();
  const boundaries = scenes.slice(1).map((scene) => scene.start);
  const activeBoundary = boundaries.find(
    (boundary) => Math.abs(frame - boundary) <= 7,
  );

  if (activeBoundary === undefined) {
    return null;
  }

  return (
    <AbsoluteFill
      style={{
        backgroundColor: "#020617",
        opacity: interpolate(
          frame,
          [activeBoundary - 7, activeBoundary, activeBoundary + 7],
          [0, 0.94, 0],
          clampOptions,
        ),
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          position: "absolute",
          top: 0,
          bottom: 0,
          width: 6,
          left: `${interpolate(
            frame,
            [activeBoundary - 7, activeBoundary + 7],
            [8, 92],
            clampOptions,
          )}%`,
          background:
            "linear-gradient(180deg, transparent, #67E8F9, transparent)",
          boxShadow: "0 0 40px rgba(103,232,249,0.65)",
        }}
      />
    </AbsoluteFill>
  );
};

const AudioTracks: React.FC = () => {
  return (
    <>
      <Audio src={staticFile("audio/ambient-score.wav")} volume={0.13} />
      {scenes.map((scene) => (
        <Sequence
          key={scene.voice}
          from={scene.start + 5}
          durationInFrames={Math.max(1, scene.duration - 5)}
          name={`Voice ${scene.number}`}
        >
          <Audio
            src={staticFile(`audio/voiceover/${scene.voice}`)}
            volume={1}
          />
        </Sequence>
      ))}
    </>
  );
};

const BrandBug: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <div
      style={{
        position: "absolute",
        left: 40,
        top: 34,
        display: "flex",
        alignItems: "center",
        gap: 12,
        color: "#0F172A",
        fontSize: 23,
        fontWeight: 820,
        opacity: interpolate(
          frame,
          [450, 468, 4860, 4890],
          [0, 0.95, 0.95, 0],
          clampOptions,
        ),
        background: "rgba(255,255,255,0.82)",
        border: "1px solid rgba(15,23,42,0.08)",
        borderRadius: 16,
        padding: "10px 14px",
        backdropFilter: "blur(16px)",
        boxShadow: "0 12px 36px rgba(15,23,42,0.08)",
      }}
    >
      <BrainCircuit size={27} color="#5B5CEB" />
      知维 OS
    </div>
  );
};

export const ZhiweiFilm: React.FC = () => {
  return (
    <AbsoluteFill
      style={{
        backgroundColor: "#020617",
        fontFamily:
          '"Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", Arial, sans-serif',
      }}
    >
      {scenes.map((scene) => (
        <Sequence
          key={scene.id}
          from={scene.start}
          durationInFrames={scene.duration}
          name={`${scene.number} ${scene.title}`}
        >
          <SceneContent scene={scene} />
        </Sequence>
      ))}
      <AudioTracks />
      <BrandBug />
      <BoundaryFlashes />
      <Captions />
    </AbsoluteFill>
  );
};
