"use client";

import { useRef, useEffect } from "react";

// ── Starfield config — each layer has its own star count, size range, opacity, cyan%, and parallax drift
interface LayerSpec { count: number; minSz: number; maxSz: number; aLo: number; aHi: number; cyanPct: number; drift: number; }

const LAYERS: LayerSpec[] = [
  { count: 90, minSz: 0.4, maxSz: 1.1, aLo: 0.06, aHi: 0.20, cyanPct: 0,    drift: 2.0  },  // deep
  { count: 60, minSz: 0.6, maxSz: 1.4, aLo: 0.10, aHi: 0.30, cyanPct: 0,    drift: 3.5  },  // far
  { count: 40, minSz: 0.8, maxSz: 2.0, aLo: 0.14, aHi: 0.40, cyanPct: 0.08, drift: 6.0  },  // mid
  { count: 20, minSz: 1.0, maxSz: 2.6, aLo: 0.18, aHi: 0.50, cyanPct: 0.15, drift: 9.0  },  // near
  { count: 6,  minSz: 1.4, maxSz: 3.2, aLo: 0.25, aHi: 0.60, cyanPct: 0.40, drift: 12.0 },  // focus
];

interface StarDatum { left: string; top: string; size: string; alpha: number; delay: string; isCyan: boolean; }

function genStars(l: LayerSpec): StarDatum[] {
  return Array.from({ length: l.count }, (_, i) => ({
    left:    `${((i * 61 + 17)  % 1000) / 10}%`,
    top:     `${((i * 89 + 31)  % 1000) / 10}%`,
    size:    `${(l.minSz + (i % 100) * ((l.maxSz - l.minSz) / 99)).toFixed(2)}px`,
    alpha:   l.aLo + ((i * 7 + 3) % 100) * ((l.aHi - l.aLo) / 99),
    delay:   `${((i * 1.37) % 5).toFixed(2)}s`,
    isCyan:  l.cyanPct > 0 && (i % Math.ceil(1 / l.cyanPct)) === 0,
  }));
}

// ── CSS-generated gradient blob positions (canvas centre at 50/50) ──
const NEBULA_BLOBS = [
  // [cx%, cy%, rxPx, ryPx, color, opacity]
  { cx: 28, cy: 38, rx: 520, ry: 340, color: "91,141,238", alpha: 0.07 },
  { cx: 68, cy: 30, rx: 450, ry: 300, color: "139,92,246", alpha: 0.05 },
  { cx: 55, cy: 62, rx: 480, ry: 320, color: "99,102,241", alpha: 0.06 },
  { cx: 18, cy: 72, rx: 380, ry: 280, color: "168,85,247", alpha: 0.04 },
  { cx: 78, cy: 68, rx: 340, ry: 260, color: "59,130,246", alpha: 0.05 },
  { cx: 48, cy: 48, rx: 600, ry: 380, color: "79,99,200", alpha: 0.03 },
];

interface Props {
  intensity: number;          // parallax drift scalar, -2 … 2
  focusActive: boolean;        // adds central focus glow when a node is selected
}

export function KnowledgeGraphBackground({ intensity, focusActive }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // ── Canvas particle layer (mid + near) ──
  useEffect(() => {
    const cvs = canvasRef.current;
    if (!cvs) return;
    const ctx = cvs.getContext("2d");
    if (!ctx) return;

    let raf = 0;
    let w = 0, h = 0;

    // Pre-generate particle pool (fixed seed)
    const particles = Array.from({ length: 55 }, (_, i) => ({
      x: ((i * 67 + 11) % 1000) / 1000,
      y: ((i * 53 + 37) % 1000) / 1000,
      r: 0.3 + (i % 10) * 0.12,
      a: 0.15 + (i % 14) * 0.04,
      speed: 0.00004 + (i % 8) * 0.00002,
      phase: (i * 0.74) % (Math.PI * 2),
      isBright: i % 13 === 0,
    }));

    function resize() {
      const rect = cvs!.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2); // cap for perf
      w = rect.width; h = rect.height;
      cvs!.width = w * dpr;
      cvs!.height = h * dpr;
      cvs!.style.width = `${w}px`;
      cvs!.style.height = `${h}px`;
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    resize();
    window.addEventListener("resize", resize);

    let t = 0;
    function frame() {
      t += 1;
      ctx!.clearRect(0, 0, w, h);

      const cx = w * 0.5;
      const cy = h * 0.5;

      for (const p of particles) {
        // extremely slow orbital drift around canvas centre
        const angle = p.phase + t * p.speed;
        const rx = w * 0.52;
        const ry = h * 0.52;
        const px = cx + Math.cos(angle) * rx * (0.3 + p.x * 0.7);
        const py = cy + Math.sin(angle) * ry * (0.3 + p.y * 0.7);

        const alpha = p.a + Math.sin(t * 0.008 + p.phase) * 0.03;

        ctx!.beginPath();
        ctx!.arc(px, py, p.r, 0, Math.PI * 2);
        ctx!.fillStyle = p.isBright
          ? `rgba(91,141,238,${alpha.toFixed(3)})`
          : `rgba(196,181,253,${alpha.toFixed(3)})`;
        ctx!.fill();

        // subtle glow for brighter particles
        if (p.isBright) {
          ctx!.beginPath();
          ctx!.arc(px, py, p.r * 2.5, 0, Math.PI * 2);
          ctx!.fillStyle = `rgba(91,141,238,${(alpha * 0.25).toFixed(3)})`;
          ctx!.fill();
        }
      }

      raf = requestAnimationFrame(frame);
    }

    raf = requestAnimationFrame(frame);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return (
    <div
      className="absolute inset-0 overflow-hidden pointer-events-none select-none"
      style={{
        // Deepest base — multilayered radial-gradient core
        background: `
          radial-gradient(ellipse 80% 70% at 50% 50%, rgba(255,255,255,0.92) 0%, #f8fafc 100%),
          radial-gradient(ellipse 55% 45% at 42% 48%, rgba(99,102,241,0.10) 0%, transparent 100%),
          radial-gradient(ellipse 40% 35% at 45% 55%, rgba(139,92,246,0.08) 0%, transparent 100%)
        `,
      }}
    >
      {/* ═══ Layer 0 — SVG Noise grain (ultra-subtle filmic texture) ═══ */}
      <svg className="absolute inset-0 w-full h-full opacity-[0.025] pointer-events-none" aria-hidden="true">
        <defs>
          <filter id="kg-grain">
            <feTurbulence type="fractalNoise" baseFrequency="0.72" numOctaves="3" stitchTiles="stitch" />
            <feColorMatrix type="saturate" values="0" />
          </filter>
          <filter id="kg-grain-fine">
            <feTurbulence type="fractalNoise" baseFrequency="1.15" numOctaves="2" stitchTiles="stitch" />
            <feColorMatrix type="saturate" values="0" />
          </filter>
        </defs>
        <rect width="100%" height="100%" filter="url(#kg-grain)" />
        <rect width="100%" height="100%" filter="url(#kg-grain-fine)" opacity="0.5" />
      </svg>

      {/* ═══ Layer 1 — Deep Stars (distant, slowest drift) ═══ */}
      <div
        className="absolute inset-0"
        style={{ transform: `translate(${intensity * -LAYERS[0].drift}px, ${intensity * -(LAYERS[0].drift + 0.5)}px)`, transition: "transform 1500ms ease-out" }}
      >
        {genStars(LAYERS[0]).map((s, i) => (
          <div key={`dp${i}`} className="absolute rounded-full"
            style={{
              left: s.left, top: s.top, width: s.size, height: s.size,
              backgroundColor: "#A78BFA", opacity: s.alpha,
              animation: `pulse ${5 + (i % 5)}s ease-in-out infinite`, animationDelay: s.delay,
            }}
          />
        ))}
      </div>

      {/* ═══ Layer 2 — Far Stars (medium distance) ═══ */}
      <div
        className="absolute inset-0"
        style={{ transform: `translate(${intensity * -LAYERS[1].drift}px, ${intensity * -(LAYERS[1].drift + 0.5)}px)`, transition: "transform 1300ms ease-out" }}
      >
        {genStars(LAYERS[1]).map((s, i) => (
          <div key={`fr${i}`} className="absolute rounded-full"
            style={{
              left: s.left, top: s.top, width: s.size, height: s.size,
              backgroundColor: s.isCyan ? "#5B8DEE" : "#B4A6F5",
              opacity: s.alpha,
              boxShadow: s.isCyan ? "0 0 1px rgba(91,141,238,0.35)" : "none",
              animation: `pulse ${4 + (i % 4)}s ease-in-out infinite`, animationDelay: s.delay,
            }}
          />
        ))}
      </div>

      {/* ═══ Layer 3 — Mid Stars + faint connection lines ═══ */}
      <div
        className="absolute inset-0"
        style={{ transform: `translate(${intensity * -LAYERS[2].drift}px, ${intensity * -(LAYERS[2].drift + 1)}px)`, transition: "transform 1100ms ease-out" }}
      >
        {genStars(LAYERS[2]).map((s, i) => (
          <div key={`md${i}`} className="absolute rounded-full"
            style={{
              left: s.left, top: s.top, width: s.size, height: s.size,
              backgroundColor: s.isCyan ? "#5B8DEE" : "#C4B5FD",
              opacity: s.alpha,
              boxShadow: s.isCyan
                ? "0 0 1.5px rgba(91,141,238,0.55), 0 0 3px rgba(91,141,238,0.2)"
                : "0 0 1px rgba(196,181,253,0.4)",
              animation: `pulse ${3.5 + (i % 3) * 1.2}s ease-in-out infinite`, animationDelay: s.delay,
            }}
          />
        ))}
      </div>

      {/* ═══ Layer 4 — Near Stars (brightest specular points) ═══ */}
      <div
        className="absolute inset-0"
        style={{ transform: `translate(${intensity * -LAYERS[3].drift}px, ${intensity * -(LAYERS[3].drift + 1)}px)`, transition: "transform 900ms ease-out" }}
      >
        {genStars(LAYERS[3]).map((s, i) => (
          <div key={`nr${i}`} className="absolute rounded-full"
            style={{
              left: s.left, top: s.top, width: s.size, height: s.size,
              backgroundColor: s.isCyan ? "#6BA5F7" : "#D4C9FF",
              opacity: s.alpha,
              boxShadow: s.isCyan
                ? "0 0 2px rgba(107,165,247,0.6), 0 0 5px rgba(107,165,247,0.25)"
                : "0 0 2px rgba(212,201,255,0.5)",
              animation: `pulse ${3 + (i % 2) * 1.8}s ease-in-out infinite`, animationDelay: s.delay,
            }}
          />
        ))}
      </div>

      {/* ═══ Layer 5 — Focus Stars (very sparse, brightest) ═══ */}
      <div
        className="absolute inset-0"
        style={{ transform: `translate(${intensity * -LAYERS[4].drift}px, ${intensity * -(LAYERS[4].drift + 1)}px)`, transition: "transform 750ms ease-out" }}
      >
        {genStars(LAYERS[4]).map((s, i) => (
          <div key={`fc${i}`} className="absolute rounded-full"
            style={{
              left: s.left, top: s.top, width: s.size, height: s.size,
              backgroundColor: s.isCyan ? "#7BB5F7" : "#E0D8FF",
              opacity: s.alpha,
              boxShadow: s.isCyan
                ? "0 0 3px rgba(123,181,247,0.7), 0 0 8px rgba(123,181,247,0.3)"
                : "0 0 3px rgba(224,216,255,0.55)",
              animation: `pulse ${2.5 + (i % 2) * 1.5}s ease-in-out infinite`, animationDelay: s.delay,
            }}
          />
        ))}
      </div>

      {/* ═══ Layer 6 — Nebula ambient blobs (CSS radial-gradient overlay) ═══ */}
      <div
        className="absolute inset-0 opacity-35 pointer-events-none"
        style={{
          background: NEBULA_BLOBS.map(b =>
            `radial-gradient(ellipse ${b.rx}px ${b.ry}px at ${b.cx}% ${b.cy}%, rgba(${b.color},${b.alpha}) 0%, transparent 75%)`
          ).join(", "),
        }}
      />

      {/* ═══ Layer 7 — Faint coordinate grid ═══ */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          backgroundImage: `
            linear-gradient(rgba(120,120,170,0.016) 1px, transparent 1px),
            linear-gradient(90deg, rgba(120,120,170,0.016) 1px, transparent 1px)
          `,
          backgroundSize: "64px 64px",
        }}
      />

      {/* ═══ Layer 8 — Constellation highlight dots at grid intersections (very rare) ═══ */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          backgroundImage: `
            radial-gradient(circle, rgba(91,141,238,0.12) 1px, transparent 1px)
          `,
          backgroundSize: "192px 192px",
          backgroundPosition: "32px 32px",
        }}
      />

      {/* ═══ Layer 9 — Canvas particles (subtle orbital drift) ═══ */}
      <canvas
        ref={canvasRef}
        className="absolute inset-0 w-full h-full pointer-events-none"
        style={{ opacity: 0.55 }}
        aria-hidden="true"
      />

      {/* ═══ Layer 10 — Central focus glow (only when a node is focused) ═══ */}
      <div
        className="absolute inset-0 pointer-events-none transition-opacity duration-700"
        style={{
          opacity: focusActive ? 1 : 0,
          background: `
            radial-gradient(ellipse 500px 350px at 50% 50%, rgba(91,141,238,0.10) 0%, rgba(91,141,238,0.03) 35%, transparent 70%),
            radial-gradient(ellipse 300px 200px at 50% 50%, rgba(139,150,255,0.06) 0%, transparent 100%)
          `,
        }}
      />
    </div>
  );
}
