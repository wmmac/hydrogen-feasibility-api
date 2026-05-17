from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # for MVP/testing only
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class FeasibilityRequest(BaseModel):
    projectName: str = Field(..., min_length=1, max_length=200)
    capacityKgPerDay: float = Field(..., ge=0)
    elecCostPerMWh: float = Field(..., ge=0)
    tariffPerUnit: float = Field(..., ge=0)
    capexTotal: float = Field(..., ge=0)
    omAnnual: float = Field(..., ge=0)
    lifetimeYears: int = Field(..., ge=1)
    schemes: List[str] = []


class BaseCaseResult(BaseModel):
    LCOH: float
    npv: float
    irr: float
    annualKg: float
    annualRevenue: float
    annualCosts: float
    annualNetCash: float


class FeasibilityResponse(BaseModel):
    success: bool
    message: str
    baseCase: BaseCaseResult
    inputs: FeasibilityRequest
    scenarios: list = []
    recommendations: list = []


def calculate_base_feasibility(payload: FeasibilityRequest) -> dict:
    days_per_year = 365
    kwh_per_kg = 50
    vat_pct = 0.07
    levy_pct = 0.336
    price_per_kg = 5
    discount_rate = 0.08

    annual_kg = payload.capacityKgPerDay * days_per_year
    total_kg_lifetime = annual_kg * payload.lifetimeYears

    spread_capex_per_kg = payload.capexTotal / total_kg_lifetime if total_kg_lifetime > 0 else 0
    energy_cost_per_kg = (payload.elecCostPerMWh / 1000) * kwh_per_kg
    tariff_per_kg = payload.tariffPerUnit

    subsidy_per_kg = 0
    if "UK_CfD" in payload.schemes:
        subsidy_per_kg += kwh_per_kg * 0.025
    if "RHI" in payload.schemes:
        subsidy_per_kg += kwh_per_kg * 0.0125
    if "Carbon_Credit" in payload.schemes:
        subsidy_per_kg += 0.025 * kwh_per_kg

    non_comm_per_kg = (spread_capex_per_kg + energy_cost_per_kg) * (vat_pct + levy_pct)

    lcoh = spread_capex_per_kg + energy_cost_per_kg + non_comm_per_kg + tariff_per_kg - subsidy_per_kg

    annual_revenue = price_per_kg * annual_kg
    annual_costs = lcoh * annual_kg + payload.omAnnual
    annual_net_cash = annual_revenue - annual_costs

    npv = -payload.capexTotal
    for year in range(1, payload.lifetimeYears + 1):
        npv += annual_net_cash / ((1 + discount_rate) ** year)

    irr = 0.1
    step = 0.1
    for _ in range(20):
        test_npv = -payload.capexTotal
        for year in range(1, payload.lifetimeYears + 1):
            test_npv += annual_net_cash / ((1 + irr) ** year)
        irr = irr + step if test_npv > 0 else irr - step
        step /= 2

    return {
        "LCOH": round(lcoh, 4),
        "npv": round(npv, 4),
        "irr": round(irr, 6),
        "annualKg": round(annual_kg, 4),
        "annualRevenue": round(annual_revenue, 4),
        "annualCosts": round(annual_costs, 4),
        "annualNetCash": round(annual_net_cash, 4),
    }


@app.get("/health")
def health():
    return {"success": True, "message": "API is healthy"}


@app.post("/calculate", response_model=FeasibilityResponse)
def calculate(payload: FeasibilityRequest):
    try:
        base_case = calculate_base_feasibility(payload)

        return FeasibilityResponse(
            success=True,
            message="Calculation completed successfully.",
            baseCase=base_case,
            inputs=payload,
            scenarios=[],
            recommendations=[],
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))