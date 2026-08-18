import {Composition} from "remotion";
import {ZhiweiFilm} from "./ZhiweiFilm";

export const VIDEO_FPS = 30;
export const VIDEO_DURATION_SECONDS = 180;

export const MyComposition: React.FC = () => {
  return (
    <Composition
      id="ZhiweiOSProductFilm"
      component={ZhiweiFilm}
      durationInFrames={VIDEO_FPS * VIDEO_DURATION_SECONDS}
      fps={VIDEO_FPS}
      width={1920}
      height={1080}
    />
  );
};
