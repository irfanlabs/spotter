import type { Level, MilesByLevel } from "../types";

export const LEVELS: { level: Level; key: keyof MilesByLevel; label: string; color: string; soft: string; ink: string }[] = [
  { level: 0, key: "low", label: "Low", color: "#2F9E6E", soft: "#E3F4EC", ink: "#17694A" },
  { level: 1, key: "moderate", label: "Moderate", color: "#E3B505", soft: "#FCF4D2", ink: "#7A5E00" },
  { level: 2, key: "high", label: "High", color: "#F08A24", soft: "#FDEAD6", ink: "#8F4A05" },
  { level: 3, key: "severe", label: "Severe", color: "#D6333C", soft: "#FBE1E3", ink: "#9B1B22" },
  { level: 4, key: "no_travel", label: "No Travel", color: "#6A1B9A", soft: "#EFDDF6", ink: "#4E1073" },
];

export const levelColor = (l: number) => LEVELS[Math.max(0, Math.min(4, l))].color;
export const levelMeta = (l: number) => LEVELS[Math.max(0, Math.min(4, l))];
