import type { AnalysisResult } from "../types";
import { IconAlert, IconCheck } from "./Icons";

export function Recommendation({ result }: { result: AnalysisResult }) {
  const r = result.recommendation;
  const advised = r.travel_advised;
  return (
    <section className={`reco ${advised ? "ok" : "bad"}`} aria-label="Recommendation">
      <div className="reco-icon">{advised ? <IconCheck /> : <IconAlert />}</div>
      <div>
        <p className="reco-kicker">{advised ? "Recommended route" : "Travel not advised"}</p>
        <h2>{r.route_name}</h2>
        <ul>
          {r.reasons.map((x) => (
            <li key={x}>{x}</li>
          ))}
        </ul>
      </div>
    </section>
  );
}
