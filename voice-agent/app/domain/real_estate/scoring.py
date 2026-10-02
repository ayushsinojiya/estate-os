"""Lead score, 0–100, computed in code — never by the model — so it is explainable and stable.

  budget known                       +20
  budget fits available inventory    +15
  BHK and location known             +15
  wants possession within 6 months   +20
  visit booked                       +20
  buying for self-use                 +5
  engaged for more than 2 minutes     +5

HOT ≥ 70, WARM 40–69, COLD < 40.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ScoreInputs:
    budget_known: bool = False
    budget_fits: bool = False
    bhk_known: bool = False
    location_known: bool = False
    timeline_months: int | None = None
    ready_to_move: bool = False
    visit_booked: bool = False
    self_use: bool = False
    duration_s: float = 0.0


def lead_score(inputs: ScoreInputs) -> int:
    score = 0
    score += 20 if inputs.budget_known else 0
    score += 15 if inputs.budget_known and inputs.budget_fits else 0
    score += 15 if inputs.bhk_known and inputs.location_known else 0
    soon = inputs.ready_to_move or (inputs.timeline_months is not None and inputs.timeline_months <= 6)
    score += 20 if soon else 0
    score += 20 if inputs.visit_booked else 0
    score += 5 if inputs.self_use else 0
    score += 5 if inputs.duration_s > 120 else 0
    return min(100, score)


def temperature(score: int) -> str:
    return "HOT" if score >= 70 else "WARM" if score >= 40 else "COLD"
