import { formatDayTime } from "../lib/format";
import type { Route } from "../types";
import { RiskPill } from "./RiskBits";

interface Props {
  route: Route;
  activeIndex: number | null;
  onFocus: (index: number) => void;
}

export function CheckpointTable({ route, activeIndex, onFocus }: Props) {
  return (
    <div className="table-wrap">
      <table className="cp-table">
        <caption className="sr-only">
          Weather checkpoints for {route.name}, every {route.interval_miles} miles
        </caption>
        <thead>
          <tr>
            <th scope="col">Mile</th>
            <th scope="col">ETA</th>
            <th scope="col">Wind</th>
            <th scope="col">Rain</th>
            <th scope="col">Snow</th>
            <th scope="col">Risk</th>
          </tr>
        </thead>
        <tbody>
          {route.checkpoints.map((c) => (
            <tr key={c.index} className={activeIndex === c.index ? "active" : ""} onClick={() => onFocus(c.index)} tabIndex={0} onKeyDown={(e) => e.key === "Enter" && onFocus(c.index)}>
              <td>{Math.round(c.mile)}</td>
              <td>{formatDayTime(c.eta)}</td>
              <td>{c.weather.wind_mph.toFixed(0)} mph</td>
              <td>{c.weather.rain_in_hr.toFixed(2)}</td>
              <td>{c.weather.snow_in_hr.toFixed(1)}</td>
              <td>
                <RiskPill level={c.risk.level} />
                {c.risk.load_adjusted && <span className="load-flag" title={c.risk.drivers[0]}> load</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
