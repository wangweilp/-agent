import {readFile, writeFile} from "node:fs/promises";
import path from "node:path";

const root = path.resolve(import.meta.dirname, "..");
const inputRoot = path.join(root, "public", "audio", "voiceover");
const outputPath = path.join(root, "public", "captions.json");

const scenes = [
  {id: "01-opening", startMs: 0},
  {id: "02-positioning", startMs: 15_000},
  {id: "03-memory", startMs: 32_000},
  {id: "04-causal", startMs: 55_000},
  {id: "05-security", startMs: 78_000},
  {id: "06-management", startMs: 103_000},
  {id: "07-platform", startMs: 123_000},
  {id: "08-scenarios", startMs: 144_000},
  {id: "09-closing", startMs: 163_000},
];

const AUDIO_OFFSET_MS = 170;
const MAX_CHARS_PER_CAPTION = 18;

const parseTime = (value) => {
  const [hours, minutes, tail] = value.split(":");
  const [seconds, milliseconds] = tail.split(",");
  return (
    Number(hours) * 3_600_000 +
    Number(minutes) * 60_000 +
    Number(seconds) * 1000 +
    Number(milliseconds)
  );
};

const cleanText = (value) =>
  value
    .replaceAll("O S", "OS")
    .replaceAll("A I", "AI")
    .replaceAll("A P I", "API")
    .replaceAll("S D K", "SDK")
    .replace(/\s+/g, " ")
    .trim();

const chunkText = (value) => {
  const clauses = value.match(/[^，。！？；]+[，。！？；]?/g) ?? [value];
  const chunks = [];

  for (const clause of clauses) {
    if (clause.length <= MAX_CHARS_PER_CAPTION) {
      chunks.push(clause);
      continue;
    }

    for (let index = 0; index < clause.length; index += MAX_CHARS_PER_CAPTION) {
      chunks.push(clause.slice(index, index + MAX_CHARS_PER_CAPTION));
    }
  }

  return chunks.filter(Boolean);
};

const parseVtt = (vtt) => {
  const matcher =
    /\d+\r?\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\r?\n([\s\S]*?)(?=\r?\n\r?\n|$)/g;
  return [...vtt.matchAll(matcher)].map((match) => ({
    startMs: parseTime(match[1]),
    endMs: parseTime(match[2]),
    text: cleanText(match[3]),
  }));
};

const captions = [];

for (const scene of scenes) {
  const vtt = await readFile(path.join(inputRoot, `${scene.id}.vtt`), "utf8");
  const cues = parseVtt(vtt);

  for (const cue of cues) {
    const chunks = chunkText(cue.text);
    const totalWeight = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
    let cursor = cue.startMs;

    chunks.forEach((chunk, index) => {
      const isLast = index === chunks.length - 1;
      const share = chunk.length / totalWeight;
      const endMs = isLast
        ? cue.endMs
        : cursor + (cue.endMs - cue.startMs) * share;

      captions.push({
        text: chunk,
        startMs: Math.round(scene.startMs + AUDIO_OFFSET_MS + cursor),
        endMs: Math.round(scene.startMs + AUDIO_OFFSET_MS + endMs),
        timestampMs: null,
        confidence: null,
      });

      cursor = endMs;
    });
  }
}

await writeFile(outputPath, `${JSON.stringify(captions, null, 2)}\n`, "utf8");
console.log(`Wrote ${captions.length} captions to ${outputPath}`);
