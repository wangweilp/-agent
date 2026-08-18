import type {Caption} from "@remotion/captions";
import {useCallback, useEffect, useMemo, useState} from "react";
import {
  AbsoluteFill,
  Easing,
  interpolate,
  staticFile,
  useCurrentFrame,
  useDelayRender,
  useVideoConfig,
} from "remotion";

export const Captions: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const [captions, setCaptions] = useState<Caption[] | null>(null);
  const {delayRender, continueRender, cancelRender} = useDelayRender();
  const [handle] = useState(() => delayRender("Loading captions"));

  const loadCaptions = useCallback(async () => {
    try {
      const response = await fetch(staticFile("captions.json"));
      const data = (await response.json()) as Caption[];
      setCaptions(data);
      continueRender(handle);
    } catch (error) {
      cancelRender(error);
    }
  }, [cancelRender, continueRender, handle]);

  useEffect(() => {
    void loadCaptions();
  }, [loadCaptions]);

  const currentTimeMs = (frame / fps) * 1000;
  const active = useMemo(
    () =>
      captions?.find(
        (caption) =>
          caption.startMs <= currentTimeMs && caption.endMs > currentTimeMs,
      ) ?? null,
    [captions, currentTimeMs],
  );

  if (!active) {
    return null;
  }

  const captionFrame = ((currentTimeMs - active.startMs) / 1000) * fps;

  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-end",
        alignItems: "center",
        paddingBottom: 92,
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          minWidth: 760,
          maxWidth: 1480,
          minHeight: 76,
          borderRadius: 22,
          border: "1px solid rgba(255,255,255,0.16)",
          background:
            "linear-gradient(135deg, rgba(5,8,22,0.9), rgba(12,20,43,0.82))",
          boxShadow: "0 20px 70px rgba(2,6,23,0.3)",
          backdropFilter: "blur(20px)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "12px 108px 13px 38px",
          position: "relative",
          opacity: interpolate(captionFrame, [0, 5], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
            easing: Easing.bezier(0.16, 1, 0.3, 1),
          }),
          translate: interpolate(
            captionFrame,
            [0, 8],
            ["0px 18px", "0px 0px"],
            {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: Easing.bezier(0.16, 1, 0.3, 1),
            },
          ),
        }}
      >
        <div
          style={{
            color: "white",
            fontSize: 42,
            lineHeight: 1.25,
            fontWeight: 650,
            letterSpacing: "0.015em",
            textAlign: "center",
            whiteSpace: "pre-wrap",
          }}
        >
          {active.text}
        </div>
      </div>
    </AbsoluteFill>
  );
};
