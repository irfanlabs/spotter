import { useEffect, useRef, useState } from "react";
import { formatDayTime } from "../lib/format";
import type { HeatmapResult } from "../types";
import { IconAlert, IconPause, IconPlay, IconRefresh } from "./Icons";
import { RiskLegend } from "./RiskBits";

interface Props {
  status: "idle" | "loading" | "ready" | "error";
  data: HeatmapResult | null;
  hour: number;
  visible: boolean;
  onHour: (h: number) => void;
  onVisible: (v: boolean) => void;
  onRetry: () => void;
}

export function HeatmapControl({ status, data, hour, visible, onHour, onVisible, onRetry }: Props) {
  const [playing, setPlaying] = useState(false);
  const hourRef = useRef(hour);
  hourRef.current = hour;
  const max = data?.hours ?? 48;

  // A new forecast (or none) ends any running playback.
  useEffect(() => {
    setPlaying(false);
  }, [data]);

  useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => onHour(hourRef.current >= max ? 0 : hourRef.current + 1), 550);
    return () => clearInterval(id);
  }, [playing, max, onHour]);

  const time = data ? new Date(new Date(data.start).getTime() + hour * 3600_000).toISOString() : null;

  return (
    <div className="heat-panel" role="group" aria-label="Weather heatmap timeline">
      <div className="heat-top">
        <label className="switch">
          <input type="checkbox" checked={visible} onChange={(e) => onVisible(e.target.checked)} />
          <span /> Weather heatmap
        </label>
        <RiskLegend compact />
      </div>

      {status === "loading" && <p className="heat-note"><span className="spinner sm" /> Loading corridor forecast…</p>}
      {status === "error" && (
        <p className="heat-note err">
          <IconAlert width={16} height={16} /> Couldn't load the heatmap.
          <button className="link" onClick={onRetry}><IconRefresh width={14} height={14} /> Retry</button>
        </p>
      )}
      {status === "idle" && <p className="heat-note">Run an analysis to see the forecast along your corridor.</p>}

      {status === "ready" && data && (
        <div className="heat-slider">
          <button className="icon-btn" onClick={() => setPlaying((p) => !p)} aria-label={playing ? "Pause animation" : "Play animation"}>
            {playing ? <IconPause /> : <IconPlay />}
          </button>
          <div className="slider-col">
            <input
              type="range"
              min={0}
              max={max}
              step={1}
              value={hour}
              onChange={(e) => {
                setPlaying(false);
                onHour(Number(e.target.value));
              }}
              aria-label="Forecast hour"
              aria-valuetext={time ? `${formatDayTime(time)}, ${hour} hours after departure` : undefined}
            />
            <div className="ticks" aria-hidden>
              {[0, 12, 24, 36, 48].map((t) => (
                <span key={t}>+{t}h</span>
              ))}
            </div>
          </div>
          <div className="heat-time">
            <strong>{time && formatDayTime(time)}</strong>
            <span>{hour === 0 ? "Departure" : `+${hour} h`}</span>
          </div>
        </div>
      )}
    </div>
  );
}
