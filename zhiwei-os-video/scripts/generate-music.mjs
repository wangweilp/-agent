import {mkdir, writeFile} from "node:fs/promises";
import path from "node:path";

const SAMPLE_RATE = 48_000;
const CHANNELS = 2;
const DURATION_SECONDS = 180;
const BITS_PER_SAMPLE = 16;
const BYTES_PER_SAMPLE = BITS_PER_SAMPLE / 8;
const SAMPLE_COUNT = SAMPLE_RATE * DURATION_SECONDS;
const DATA_SIZE = SAMPLE_COUNT * CHANNELS * BYTES_PER_SAMPLE;
const outputPath = path.resolve(
  import.meta.dirname,
  "..",
  "public",
  "audio",
  "ambient-score.wav",
);

const buffer = Buffer.allocUnsafe(44 + DATA_SIZE);

buffer.write("RIFF", 0);
buffer.writeUInt32LE(36 + DATA_SIZE, 4);
buffer.write("WAVE", 8);
buffer.write("fmt ", 12);
buffer.writeUInt32LE(16, 16);
buffer.writeUInt16LE(1, 20);
buffer.writeUInt16LE(CHANNELS, 22);
buffer.writeUInt32LE(SAMPLE_RATE, 24);
buffer.writeUInt32LE(SAMPLE_RATE * CHANNELS * BYTES_PER_SAMPLE, 28);
buffer.writeUInt16LE(CHANNELS * BYTES_PER_SAMPLE, 32);
buffer.writeUInt16LE(BITS_PER_SAMPLE, 34);
buffer.write("data", 36);
buffer.writeUInt32LE(DATA_SIZE, 40);

const chordRoots = [65.41, 73.42, 87.31, 82.41, 65.41, 73.42, 87.31, 98.0];
const smoothstep = (value) => value * value * (3 - 2 * value);
const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

let randomState = 0x6d2b79f5;
const noise = () => {
  randomState = (Math.imul(randomState, 1664525) + 1013904223) >>> 0;
  return randomState / 0xffffffff - 0.5;
};

const padSample = (time, root, phaseOffset) => {
  const fifth = root * 1.498307;
  const octave = root * 2;
  return (
    Math.sin(Math.PI * 2 * root * time + phaseOffset) * 0.58 +
    Math.sin(Math.PI * 2 * fifth * time + phaseOffset * 0.7) * 0.27 +
    Math.sin(Math.PI * 2 * octave * time + phaseOffset * 1.3) * 0.15
  );
};

for (let index = 0; index < SAMPLE_COUNT; index++) {
  const time = index / SAMPLE_RATE;
  const chapter = Math.floor(time / 22.5) % chordRoots.length;
  const chapterProgress = (time % 22.5) / 22.5;
  const crossfade = smoothstep(clamp((chapterProgress - 0.82) / 0.18, 0, 1));
  const rootA = chordRoots[chapter];
  const rootB = chordRoots[(chapter + 1) % chordRoots.length];

  const padLeft =
    padSample(time, rootA, 0.12) * (1 - crossfade) +
    padSample(time, rootB, 0.12) * crossfade;
  const padRight =
    padSample(time, rootA * 1.0018, 0.68) * (1 - crossfade) +
    padSample(time, rootB * 1.0018, 0.68) * crossfade;

  const beatPhase = time % 2;
  const pulseEnvelope = Math.exp(-beatPhase * 7.2);
  const pulseTone =
    Math.sin(Math.PI * 2 * (130 + chapter * 7) * time) * pulseEnvelope;

  const shimmerPhase = time % 8;
  const shimmerEnvelope =
    shimmerPhase < 2.2
      ? Math.sin((Math.PI * shimmerPhase) / 2.2) ** 2
      : 0;
  const shimmer =
    (Math.sin(Math.PI * 2 * 659.25 * time) +
      Math.sin(Math.PI * 2 * 987.77 * time + 0.8)) *
    0.5 *
    shimmerEnvelope;

  const texture = noise() * 0.035;
  const fadeIn = smoothstep(clamp(time / 4, 0, 1));
  const fadeOut = smoothstep(clamp((DURATION_SECONDS - time) / 5, 0, 1));
  const master = fadeIn * fadeOut;

  const left = clamp(
    (padLeft * 0.34 + pulseTone * 0.08 + shimmer * 0.025 + texture) * master,
    -1,
    1,
  );
  const right = clamp(
    (padRight * 0.34 + pulseTone * 0.07 + shimmer * 0.03 - texture) * master,
    -1,
    1,
  );

  const offset = 44 + index * CHANNELS * BYTES_PER_SAMPLE;
  buffer.writeInt16LE(Math.round(left * 32767), offset);
  buffer.writeInt16LE(Math.round(right * 32767), offset + BYTES_PER_SAMPLE);
}

await mkdir(path.dirname(outputPath), {recursive: true});
await writeFile(outputPath, buffer);
console.log(`Wrote ${DURATION_SECONDS}s ambient score to ${outputPath}`);
