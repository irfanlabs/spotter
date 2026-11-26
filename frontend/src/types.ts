export interface Place {
  label: string;
  lat: number;
  lon: number;
}

export type Level = 0 | 1 | 2 | 3 | 4;

export interface Risk {
  level: Level;
  label: string;
  factors: { wind: Level; rain: Level; snow: Level };
  load_adjusted: boolean;
  drivers: string[];
}

export interface Checkpoint {
  index: number;
  lat: number;
  lon: number;
  mile: number;
  eta: string;
  segment_miles: number;
  weather: { wind_mph: number; rain_in_hr: number; snow_in_hr: number };
  risk: Risk;
}

export interface MilesByLevel {
  low: number;
  moderate: number;
  high: number;
  severe: number;
  no_travel: number;
}

export interface Route {
  id: string;
  name: string;
  geometry: string;
  distance_mi: number;
  duration_s: number;
  departure: string;
  arrival: string;
  interval_miles: number;
  miles_by_level: MilesByLevel;
  avg_risk: number;
  max_level: Level;
  max_level_label: string;
  rank: number;
  recommended: boolean;
  tags: string[];
  summary: string;
  checkpoints: Checkpoint[];
}

export interface AnalysisResult {
  request: { origin: Place; destination: Place; departure: string; load_weight_lb: number };
  recommendation: { route_id: string; route_name: string; reasons: string[]; travel_advised: boolean };
  routes: Route[];
  meta: { generated_at: string; weather_source: string; routing_source: string; truck_time_factor: number };
}

export interface HeatCell {
  lat: number;
  lon: number;
  levels: number[]; // per hour: 0-4 risk level, or -1 when there is no forecast
  wind: number[];
  rain: number[];
  snow: number[];
}

export interface HeatmapResult {
  start: string;
  hours: number;
  cell_radius_mi: number;
  cells: HeatCell[];
}

export interface AnalyzeRequest {
  origin: Place;
  destination: Place;
  departure: string;
  load_weight_lb: number;
  interval_miles: 10 | 25 | 50 | null;
}
