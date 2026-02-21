"""
PowerTraderAI+ Cost Management System

Tracks operational costs, performance metrics, and ROI analysis
for sustainable trading operations.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple


class CostCategory(Enum):
    """Cost categories for expense tracking"""

    INFRASTRUCTURE = "infrastructure"
    DATA_FEEDS = "data_feeds"
    EXCHANGE_FEES = "exchange_fees"
    COMPLIANCE = "compliance"
    INSURANCE = "insurance"
    PERSONNEL = "personnel"
    SOFTWARE = "software"
    LEGAL = "legal"


class PerformanceTier(Enum):
    """Performance tiers for cost optimization"""

    BUDGET = "budget"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


@dataclass
class CostItem:
    """Individual cost item tracking"""

    category: CostCategory
    description: str
    amount: float
    frequency: str  # 'monthly', 'annual', 'per_trade', 'one_time'
    is_variable: bool = False
    threshold_dependent: Optional[str] = None  # e.g., 'user_count', 'volume'


@dataclass
class PerformanceMetrics:
    """Trading performance metrics for ROI calculation"""

    total_return: float
    annualized_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    total_trades: int
    capital_deployed: float


@dataclass
class CostBreakdown:
    """Monthly cost breakdown by category"""

    infrastructure: float = 0.0
    data_feeds: float = 0.0
    exchange_fees: float = 0.0
    compliance: float = 0.0
    insurance: float = 0.0
    personnel: float = 0.0
    software: float = 0.0
    legal: float = 0.0

    @property
    def total_monthly(self) -> float:
        return (
            self.infrastructure
            + self.data_feeds
            + self.exchange_fees
            + self.compliance
            + self.insurance
            + self.personnel
            + self.software
            + self.legal
        )

    @property
    def total_annual(self) -> float:
        return self.total_monthly * 12


class CostManager:
    """
    Comprehensive cost management and ROI tracking system

    Monitors operational costs, calculates break-even points,
    and optimizes cost structure based on performance.
    """

    def __init__(self, tier: PerformanceTier = PerformanceTier.BUDGET):
        self.tier = tier
        self.cost_items: List[CostItem] = []
        self.monthly_costs: CostBreakdown = CostBreakdown()
        self.performance_history: List[PerformanceMetrics] = []

        # Cost configurations by tier
        self._initialize_cost_structure()

        # Logger
        self.logger = logging.getLogger(__name__)

    def _initialize_cost_structure(self):
        """Initialize cost structure based on performance tier"""

        if self.tier == PerformanceTier.BUDGET:
            self._setup_budget_costs()
        elif self.tier == PerformanceTier.PROFESSIONAL:
            self._setup_professional_costs()
        elif self.tier == PerformanceTier.ENTERPRISE:
            self._setup_enterprise_costs()

    def _setup_budget_costs(self):
        """Setup budget tier cost structure"""
        budget_costs = [
            # Infrastructure
            CostItem(CostCategory.INFRASTRUCTURE, "VPS Hosting", 75, "monthly"),
            CostItem(CostCategory.INFRASTRUCTURE, "Basic Monitoring", 25, "monthly"),
            CostItem(CostCategory.INFRASTRUCTURE, "SSL Certificate", 10, "monthly"),
            # Data Feeds
            CostItem(CostCategory.DATA_FEEDS, "Free/Delayed Data", 0, "monthly"),
            CostItem(CostCategory.DATA_FEEDS, "Basic API Access", 50, "monthly"),
            # Exchange Fees (variable)
            CostItem(
                CostCategory.EXCHANGE_FEES,
                "Trading Commissions",
                0.1,
                "per_trade",
                True,
            ),
            # Software
            CostItem(CostCategory.SOFTWARE, "Basic Tools", 20, "monthly"),
            # Insurance (annual)
            CostItem(CostCategory.INSURANCE, "Basic Liability", 500, "annual"),
            # Legal (one-time + annual)
            CostItem(CostCategory.LEGAL, "Initial Legal Review", 2000, "one_time"),
            CostItem(CostCategory.LEGAL, "Annual Compliance", 1000, "annual"),
        ]

        self.cost_items.extend(budget_costs)
        self.monthly_costs = CostBreakdown(
            infrastructure=110,
            data_feeds=50,
            exchange_fees=0,  # Variable
            software=20,
            insurance=42,  # $500/year ÷ 12
            legal=83,  # $1000/year ÷ 12
        )

    def _setup_professional_costs(self):
        """Setup professional tier cost structure"""
        professional_costs = [
            # Infrastructure
            CostItem(
                CostCategory.INFRASTRUCTURE, "Cloud Hosting (AWS/Azure)", 300, "monthly"
            ),
            CostItem(CostCategory.INFRASTRUCTURE, "Database Service", 150, "monthly"),
            CostItem(
                CostCategory.INFRASTRUCTURE, "Monitoring & Alerts", 100, "monthly"
            ),
            CostItem(CostCategory.INFRASTRUCTURE, "Backup & Recovery", 75, "monthly"),
            # Data Feeds
            CostItem(CostCategory.DATA_FEEDS, "Real-time Crypto Data", 300, "monthly"),
            CostItem(CostCategory.DATA_FEEDS, "Stock Market Data", 200, "monthly"),
            CostItem(CostCategory.DATA_FEEDS, "News & Sentiment", 500, "monthly"),
            # Exchange Fees
            CostItem(
                CostCategory.EXCHANGE_FEES,
                "Reduced Rate Trading",
                0.05,
                "per_trade",
                True,
            ),
            # Software
            CostItem(CostCategory.SOFTWARE, "Professional Tools", 200, "monthly"),
            CostItem(CostCategory.SOFTWARE, "Security Tools", 100, "monthly"),
            CostItem(CostCategory.SOFTWARE, "Analytics Platform", 300, "monthly"),
            # Insurance
            CostItem(CostCategory.INSURANCE, "Professional Liability", 3000, "annual"),
            CostItem(CostCategory.INSURANCE, "Cyber Liability", 2000, "annual"),
            # Legal & Compliance
            CostItem(CostCategory.LEGAL, "Legal Compliance", 2000, "monthly"),
            CostItem(CostCategory.LEGAL, "Regulatory Updates", 500, "monthly"),
            # Personnel (part-time)
            CostItem(CostCategory.PERSONNEL, "Part-time Developer", 4000, "monthly"),
        ]

        self.cost_items.extend(professional_costs)
        self.monthly_costs = CostBreakdown(
            infrastructure=625,
            data_feeds=1000,
            exchange_fees=0,  # Variable
            software=600,
            insurance=417,  # $5000/year ÷ 12
            legal=2500,
            personnel=4000,
        )

    def _setup_enterprise_costs(self):
        """Setup enterprise tier cost structure"""
        enterprise_costs = [
            # Infrastructure
            CostItem(CostCategory.INFRASTRUCTURE, "Enterprise Cloud", 2000, "monthly"),
            CostItem(
                CostCategory.INFRASTRUCTURE, "Multi-region Setup", 1000, "monthly"
            ),
            CostItem(
                CostCategory.INFRASTRUCTURE, "Enterprise Monitoring", 500, "monthly"
            ),
            CostItem(CostCategory.INFRASTRUCTURE, "Disaster Recovery", 800, "monthly"),
            # Data Feeds
            CostItem(
                CostCategory.DATA_FEEDS, "Enterprise Data Package", 3000, "monthly"
            ),
            CostItem(CostCategory.DATA_FEEDS, "Alternative Data", 2000, "monthly"),
            CostItem(CostCategory.DATA_FEEDS, "News & Analytics", 1500, "monthly"),
            # Exchange Fees
            CostItem(
                CostCategory.EXCHANGE_FEES,
                "Institutional Rates",
                0.02,
                "per_trade",
                True,
            ),
            # Software
            CostItem(
                CostCategory.SOFTWARE, "Enterprise Software Suite", 2000, "monthly"
            ),
            CostItem(
                CostCategory.SOFTWARE, "Security & Compliance Tools", 1000, "monthly"
            ),
            # Personnel
            CostItem(CostCategory.PERSONNEL, "Engineering Team", 50000, "monthly"),
            CostItem(CostCategory.PERSONNEL, "Operations Team", 20000, "monthly"),
            CostItem(CostCategory.PERSONNEL, "Compliance Team", 15000, "monthly"),
            # Compliance
            CostItem(CostCategory.COMPLIANCE, "SEC Registration", 100000, "one_time"),
            CostItem(CostCategory.COMPLIANCE, "Audit Costs", 150000, "annual"),
            CostItem(CostCategory.COMPLIANCE, "Compliance Systems", 200000, "annual"),
            # Insurance
            CostItem(
                CostCategory.INSURANCE, "Enterprise Insurance Package", 50000, "annual"
            ),
            # Legal
            CostItem(CostCategory.LEGAL, "Legal Team", 10000, "monthly"),
        ]

        self.cost_items.extend(enterprise_costs)
        self.monthly_costs = CostBreakdown(
            infrastructure=4300,
            data_feeds=6500,
            exchange_fees=0,  # Variable
            software=3000,
            personnel=85000,
            compliance=29167,  # ($150k + $200k)/12
            insurance=4167,  # $50k/year ÷ 12
            legal=10000,
        )

    def calculate_monthly_costs(self, trading_volume: float = 0) -> CostBreakdown:
        """
        Calculate total monthly costs including variable costs

        Args:
            trading_volume: Monthly trading volume for variable cost calculation
        """
        costs = CostBreakdown()

        for item in self.cost_items:
            monthly_cost = 0

            if item.frequency == "monthly":
                monthly_cost = item.amount
            elif item.frequency == "annual":
                monthly_cost = item.amount / 12
            elif item.frequency == "per_trade" and item.is_variable:
                # Estimate trades per month based on volume
                estimated_trades = trading_volume / 1000  # Rough estimate
                monthly_cost = item.amount * estimated_trades
            elif item.frequency == "one_time":
                # Amortize one-time costs over 12 months
                monthly_cost = item.amount / 12

            # Add to appropriate category
            if item.category == CostCategory.INFRASTRUCTURE:
                costs.infrastructure += monthly_cost
            elif item.category == CostCategory.DATA_FEEDS:
                costs.data_feeds += monthly_cost
            elif item.category == CostCategory.EXCHANGE_FEES:
                costs.exchange_fees += monthly_cost
            elif item.category == CostCategory.COMPLIANCE:
                costs.compliance += monthly_cost
            elif item.category == CostCategory.INSURANCE:
                costs.insurance += monthly_cost
            elif item.category == CostCategory.PERSONNEL:
                costs.personnel += monthly_cost
            elif item.category == CostCategory.SOFTWARE:
                costs.software += monthly_cost
            elif item.category == CostCategory.LEGAL:
                costs.legal += monthly_cost

        return costs

    def calculate_break_even_return(
        self, capital: float, trading_volume: float = 0
    ) -> Tuple[float, Dict]:
        """
        Calculate required annual return to break even

        Args:
            capital: Trading capital available
            trading_volume: Monthly trading volume

        Returns:
            (required_annual_return, cost_breakdown)
        """
        monthly_costs = self.calculate_monthly_costs(trading_volume)
        annual_costs = monthly_costs.total_annual

        required_return = annual_costs / capital if capital > 0 else float("inf")

        breakdown = {
            "annual_costs": annual_costs,
            "monthly_costs": monthly_costs.total_monthly,
            "required_return_pct": required_return * 100,
            "cost_breakdown": {
                "infrastructure": monthly_costs.infrastructure * 12,
                "data_feeds": monthly_costs.data_feeds * 12,
                "exchange_fees": monthly_costs.exchange_fees * 12,
                "compliance": monthly_costs.compliance * 12,
                "insurance": monthly_costs.insurance * 12,
                "personnel": monthly_costs.personnel * 12,
                "software": monthly_costs.software * 12,
                "legal": monthly_costs.legal * 12,
            },
        }

        return required_return, breakdown

    def analyze_roi(
        self, performance: PerformanceMetrics, trading_volume: float = 0
    ) -> Dict:
        """
        Analyze return on investment including all costs

        Args:
            performance: Trading performance metrics
            trading_volume: Monthly trading volume

        Returns:
            ROI analysis dictionary
        """
        monthly_costs = self.calculate_monthly_costs(trading_volume)
        annual_costs = monthly_costs.total_annual

        # Calculate net returns after costs
        gross_return = performance.total_return
        net_return = gross_return - annual_costs
        net_return_pct = (
            net_return / performance.capital_deployed
            if performance.capital_deployed > 0
            else 0
        )

        # Calculate cost efficiency metrics
        cost_per_trade = (
            annual_costs / performance.total_trades
            if performance.total_trades > 0
            else 0
        )
        cost_ratio = (
            annual_costs / performance.capital_deployed
            if performance.capital_deployed > 0
            else 0
        )

        return {
            "gross_return": gross_return,
            "net_return": net_return,
            "net_return_pct": net_return_pct * 100,
            "total_costs": annual_costs,
            "cost_ratio": cost_ratio * 100,
            "cost_per_trade": cost_per_trade,
            "break_even_return_pct": (annual_costs / performance.capital_deployed)
            * 100,
            "is_profitable": net_return > 0,
            "efficiency_score": performance.sharpe_ratio / cost_ratio
            if cost_ratio > 0
            else 0,
        }

    def optimize_tier_selection(self, capital: float, expected_return: float) -> Dict:
        """
        Recommend optimal tier based on capital and expected returns

        Args:
            capital: Available trading capital
            expected_return: Expected annual return percentage

        Returns:
            Tier recommendation analysis
        """
        recommendations = {}

        for tier in PerformanceTier:
            # Create temporary cost manager for each tier
            temp_manager = CostManager(tier)
            monthly_costs = temp_manager.calculate_monthly_costs()
            annual_costs = monthly_costs.total_annual

            required_return = annual_costs / capital if capital > 0 else float("inf")

            recommendations[tier.value] = {
                "annual_costs": annual_costs,
                "required_return_pct": required_return * 100,
                "expected_profit": (expected_return - required_return) * capital,
                "feasible": expected_return > required_return,
                "margin_of_safety": (expected_return - required_return)
                / expected_return
                if expected_return > 0
                else -1,
            }

        # Find best tier
        feasible_tiers = {k: v for k, v in recommendations.items() if v["feasible"]}

        if feasible_tiers:
            best_tier = max(
                feasible_tiers.keys(),
                key=lambda x: feasible_tiers[x]["expected_profit"],
            )
        else:
            best_tier = PerformanceTier.BUDGET.value

        return {
            "recommended_tier": best_tier,
            "tier_analysis": recommendations,
            "capital": capital,
            "expected_return_pct": expected_return * 100,
        }

    def track_actual_costs(
        self, category: CostCategory, amount: float, description: str
    ):
        """Track actual costs incurred"""
        cost_record = {
            "timestamp": datetime.now().isoformat(),
            "category": category.value,
            "amount": amount,
            "description": description,
        }

        # In production, this would save to a database
        self.logger.info(f"Cost tracked: {category.value} - ${amount} - {description}")

    def generate_cost_report(self, period_months: int = 12) -> Dict:
        """Generate comprehensive cost report"""
        monthly_costs = self.calculate_monthly_costs()

        return {
            "period_months": period_months,
            "tier": self.tier.value,
            "monthly_breakdown": {
                "infrastructure": monthly_costs.infrastructure,
                "data_feeds": monthly_costs.data_feeds,
                "exchange_fees": monthly_costs.exchange_fees,
                "compliance": monthly_costs.compliance,
                "insurance": monthly_costs.insurance,
                "personnel": monthly_costs.personnel,
                "software": monthly_costs.software,
                "legal": monthly_costs.legal,
                "total": monthly_costs.total_monthly,
            },
            "annual_projection": monthly_costs.total_annual,
            "period_total": monthly_costs.total_monthly * period_months,
            "largest_cost_category": max(
                [
                    ("infrastructure", monthly_costs.infrastructure),
                    ("data_feeds", monthly_costs.data_feeds),
                    ("personnel", monthly_costs.personnel),
                    ("compliance", monthly_costs.compliance),
                    ("software", monthly_costs.software),
                    ("insurance", monthly_costs.insurance),
                    ("legal", monthly_costs.legal),
                ],
                key=lambda x: x[1],
            )[0],
        }

    def calculate_scaling_costs(self, user_multiplier: float) -> Dict:
        """Calculate costs when scaling to multiple users"""
        base_costs = self.calculate_monthly_costs()

        # Scale variable costs
        scaled_costs = CostBreakdown(
            infrastructure=base_costs.infrastructure * user_multiplier,
            data_feeds=base_costs.data_feeds
            * min(user_multiplier, 3),  # Data costs don't scale linearly
            exchange_fees=base_costs.exchange_fees * user_multiplier,
            compliance=base_costs.compliance
            + (user_multiplier - 1) * 1000,  # Additional compliance per user
            insurance=base_costs.insurance * user_multiplier,
            personnel=base_costs.personnel
            + (user_multiplier - 1) * 2000,  # Support scaling
            software=base_costs.software * user_multiplier,
            legal=base_costs.legal + (user_multiplier - 1) * 500,
        )

        return {
            "user_multiplier": user_multiplier,
            "base_monthly_cost": base_costs.total_monthly,
            "scaled_monthly_cost": scaled_costs.total_monthly,
            "cost_per_user": scaled_costs.total_monthly / user_multiplier,
            "scaling_efficiency": base_costs.total_monthly
            / scaled_costs.total_monthly
            * user_multiplier,
        }


# Example usage
if __name__ == "__main__":
    # Test different tiers
    for tier in PerformanceTier:
        print(f"\n=== {tier.value.upper()} TIER ===")

        cost_manager = CostManager(tier)
        monthly_costs = cost_manager.calculate_monthly_costs()

        print(f"Monthly costs: ${monthly_costs.total_monthly:,.2f}")
        print(f"Annual costs: ${monthly_costs.total_annual:,.2f}")

        # Break-even analysis for different capital levels
        for capital in [50000, 100000, 500000]:
            required_return, breakdown = cost_manager.calculate_break_even_return(
                capital
            )
            print(f"Capital ${capital:,}: Requires {required_return:.1%} annual return")

    # Tier optimization example
    print("\n=== TIER OPTIMIZATION ===")
    cost_manager = CostManager()
    recommendation = cost_manager.optimize_tier_selection(
        capital=200000, expected_return=0.25
    )
    print(f"Recommended tier: {recommendation['recommended_tier']}")
    print(
        f"Expected profit: ${recommendation['tier_analysis'][recommendation['recommended_tier']]['expected_profit']:,.2f}"
    )
