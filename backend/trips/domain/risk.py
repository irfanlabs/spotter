"""Weather risk classification.

Pure functions, no I/O. Implements the thresholds and load rules from the
assessment brief.

Boundary convention
-------------------
* Wind uses half-open bands with an inclusive lower bound:
  <25 Low, 25-34 Moderate, 35-44 High, 45-54 Severe, >=55 No Travel.
* Rain / snow bands are written in the brief with a ">" on the top band
  (">1.00", ">3.0"), so the upper edge of every other band is inclusive:
  rain <0.10 Low, <=0.25 Moderate, <=0.50 High, <=1.00 Severe, >1.00 No Travel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class RiskLevel(IntEnum):
    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def label(self) -> str:
        return {
            RiskLevel.LOW: "Low",
            RiskLevel.MODERATE: "Moderate",
            RiskLevel.HIGH: "High",
            RiskLevel.SEVERE: "Severe",
            RiskLevel.NO_TRAVEL: "No Travel",
        }[self]

    @property
    def key(self) -> str:
        return self.name.lower()


LEVEL_KEYS = [lvl.key for lvl in RiskLevel]

# Wind: lower bound (inclusive) of each band above Low, in mph.
WIND_BANDS = ((55.0, RiskLevel.NO_TRAVEL), (45.0, RiskLevel.SEVERE), (35.0, RiskLevel.HIGH), (25.0, RiskLevel.MODERATE))

# Rain / snow: upper bound (inclusive) of each band, in inches per hour.
# Low is strictly below the first bound.
RAIN_LOW_BELOW = 0.10
RAIN_UPPER = ((0.25, RiskLevel.MODERATE), (0.50, RiskLevel.HIGH), (1.00, RiskLevel.SEVERE))
SNOW_LOW_BELOW = 0.5
SNOW_UPPER = ((1.0, RiskLevel.MODERATE), (2.0, RiskLevel.HIGH), (3.0, RiskLevel.SEVERE))

# Load rules (lb, strict ">" per the brief).
HEAVY_LOAD_NO_TRAVEL_LB = 30_000  # with 45-54 mph wind
HEAVY_LOAD_SEVERE_LB = 40_000  # with 35-44 mph wind


def wind_level(mph: float) -> RiskLevel:
    for lower, level in WIND_BANDS:
        if mph >= lower:
            return level
    return RiskLevel.LOW


def _precip_level(value: float, low_below: float, upper) -> RiskLevel:
    if value < low_below:
        return RiskLevel.LOW
    for bound, level in upper:
        if value <= bound:
            return level
    return RiskLevel.NO_TRAVEL


def rain_level(inches_per_hour: float) -> RiskLevel:
    return _precip_level(inches_per_hour, RAIN_LOW_BELOW, RAIN_UPPER)


def snow_level(inches_per_hour: float) -> RiskLevel:
    return _precip_level(inches_per_hour, SNOW_LOW_BELOW, SNOW_UPPER)


@dataclass(frozen=True)
class RiskAssessment:
    level: RiskLevel
    wind: RiskLevel
    rain: RiskLevel
    snow: RiskLevel
    load_adjusted: bool = False
    drivers: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict:
        return {
            "level": int(self.level),
            "label": self.level.label,
            "factors": {
                "wind": int(self.wind),
                "rain": int(self.rain),
                "snow": int(self.snow),
            },
            "load_adjusted": self.load_adjusted,
            "drivers": list(self.drivers),
        }


def assess(wind_mph: float, rain_in_hr: float, snow_in_hr: float, load_lb: float) -> RiskAssessment:
    """Classify one checkpoint. The overall level is the worst single factor,
    then raised (never lowered) by the load rules."""
    wind = wind_level(wind_mph)
    rain = rain_level(rain_in_hr)
    snow = snow_level(snow_in_hr)
    level = max(wind, rain, snow)
    drivers: list[str] = []
    load_adjusted = False

    # Load rules raise the level; they never lower it. (>=55 mph is already
    # No Travel for any load via wind_level.)
    if 45 <= wind_mph < 55 and load_lb > HEAVY_LOAD_NO_TRAVEL_LB:
        level = RiskLevel.NO_TRAVEL
        load_adjusted = True
        drivers.append(f"{wind_mph:.0f} mph wind with a {load_lb:,.0f} lb load (over 30,000 lb) is No Travel")
    elif 35 <= wind_mph < 45 and load_lb > HEAVY_LOAD_SEVERE_LB:
        load_adjusted = level < RiskLevel.SEVERE
        level = max(level, RiskLevel.SEVERE)
        drivers.append(f"{wind_mph:.0f} mph wind with a {load_lb:,.0f} lb load (over 40,000 lb) is Severe")

    for name, lvl, value, unit in (
        ("Wind", wind, wind_mph, "mph"),
        ("Rain", rain, rain_in_hr, "in/hr"),
        ("Snow", snow, snow_in_hr, "in/hr"),
    ):
        if lvl >= RiskLevel.MODERATE:
            shown = f"{value:.0f}" if unit == "mph" else f"{value:.2f}"
            drivers.append(f"{name} {shown} {unit} ({lvl.label})")

    return RiskAssessment(level, wind, rain, snow, load_adjusted, tuple(drivers))
