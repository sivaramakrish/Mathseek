from datetime import datetime, timezone
from typing import Dict, Any, List
import os
from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv()

class CostTracker:
    def __init__(self):
        self.usage = {
            'input_tokens': 0,
            'output_tokens': 0,
            'cache_hits': 0,
            'cache_misses': 0
        }
        self.pricing = self._get_pricing()
        self.budget = float(os.getenv('DEEPSEEK_BUDGET', 2.0))
        self.total_cost = 0.0
        self.budget_history = []
        self.alert_history = []
        self.MIN_BUDGET = 0.1
        self.MAX_BUDGET = 100.0
        self.ALERT_THRESHOLDS = [0.8, 0.9, 0.95]  # Alert at 80%, 90%, and 95% of budget
        self.USAGE_WINDOW = 100  # Number of requests to consider for projections
        self.usage_log = []  # Store recent usage for projections

    def _get_pricing(self) -> Dict[str, float]:
        """Get current pricing based on time"""
        current_time = datetime.now(timezone.utc)
        is_discount_period = 16.5 <= current_time.hour < 24 or 0 <= current_time.hour < 0.5

        return {
            'input_cache_hit': 0.035 if is_discount_period else 0.07,
            'input_cache_miss': 0.135 if is_discount_period else 0.27,
            'output': 0.550 if is_discount_period else 1.10
        }

    def _validate_budget(self, amount: float) -> None:
        """Validate budget amount is within allowed range"""
        if amount < self.MIN_BUDGET:
            raise ValueError(f"Budget must be at least ${self.MIN_BUDGET:.2f}")
        if amount > self.MAX_BUDGET:
            raise ValueError(f"Budget cannot exceed ${self.MAX_BUDGET:.2f}")

    def _check_alerts(self) -> list:
        """Check if any budget alerts should be triggered"""
        alerts = []
        current_percentage = (self.total_cost / self.budget) * 100
        
        for threshold in self.ALERT_THRESHOLDS:
            if (current_percentage >= threshold * 100 and 
                not any(a['threshold'] == threshold for a in self.alert_history)):
                alerts.append({
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'threshold': threshold,
                    'current_cost': self.total_cost,
                    'remaining_budget': self.budget - self.total_cost
                })
        
        return alerts

    def _calculate_projection(self) -> float:
        """Calculate projected total cost based on recent usage"""
        if not self.usage_log:
            return None
            
        # Calculate average cost per request from recent usage
        avg_cost = sum(entry['cost'] for entry in self.usage_log) / len(self.usage_log)
        
        # Project based on remaining budget
        remaining_requests = (self.budget - self.total_cost) / avg_cost if avg_cost > 0 else 0
        
        return {
            'avg_cost_per_request': avg_cost,
            'estimated_remaining_requests': remaining_requests,
            'projected_total_cost': self.total_cost + (avg_cost * remaining_requests)
        }

    def track_usage(self, input_tokens: int, output_tokens: int, cache_hit: bool = False):
        """Track token usage and update statistics"""
        self.usage['input_tokens'] += input_tokens
        self.usage['output_tokens'] += output_tokens
        
        if cache_hit:
            self.usage['cache_hits'] += 1
        else:
            self.usage['cache_misses'] += 1

        # Calculate cost for this request
        pricing = self._get_pricing()
        input_cost = pricing['input_cache_hit'] * input_tokens / 1000000 if cache_hit else pricing['input_cache_miss'] * input_tokens / 1000000
        output_cost = pricing['output'] * output_tokens / 1000000
        request_cost = input_cost + output_cost
        
        # Update total cost
        self.total_cost += request_cost

        # Log this usage for projections
        self.usage_log.append({
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'cost': request_cost
        })
        
        # Keep only the last USAGE_WINDOW entries
        self.usage_log = self.usage_log[-self.USAGE_WINDOW:]

        # Check for alerts
        alerts = self._check_alerts()
        if alerts:
            self.alert_history.extend(alerts)

        # Check if we've exceeded budget
        if self.total_cost > self.budget:
            raise Exception(f"Budget exceeded! Current cost: ${self.total_cost:.2f}, Budget: ${self.budget:.2f}")

    def set_budget(self, amount: float) -> Dict[str, Any]:
        """Set new budget amount with validation and history tracking"""
        try:
            self._validate_budget(amount)
            old_budget = self.budget
            self.budget = amount
            
            # Add to budget history
            self.budget_history.append({
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'old_budget': old_budget,
                'new_budget': amount
            })
            
            # Clear alert history since budget changed
            self.alert_history = []
            
            return {
                "message": f"Budget updated from ${old_budget:.2f} to ${amount:.2f}",
                "new_budget": amount,
                "old_budget": old_budget
            }
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=str(e)
            )

    def get_budget_history(self) -> list:
        """Get budget change history"""
        return self.budget_history

    def get_alert_history(self) -> list:
        """Get budget alert history"""
        return self.alert_history

    def get_usage_projection(self) -> Dict[str, Any]:
        """Get projection of future usage based on recent patterns"""
        projection = self._calculate_projection()
        if projection:
            return {
                'avg_cost_per_request': projection['avg_cost_per_request'],
                'estimated_remaining_requests': projection['estimated_remaining_requests'],
                'projected_total_cost': projection['projected_total_cost'],
                'current_cost': self.total_cost,
                'budget': self.budget,
                'remaining_budget': self.budget - self.total_cost
            }
        return {
            'message': 'Not enough data for projection'
        }

    def calculate_cost(self) -> Dict[str, Any]:
        """Calculate total cost based on usage"""
        pricing = self._get_pricing()
        
        # Calculate costs in USD
        input_cost = (
            (self.usage['cache_hits'] * pricing['input_cache_hit'] * 1000000) +
            (self.usage['cache_misses'] * pricing['input_cache_miss'] * 1000000)
        )
        
        output_cost = self.usage['output_tokens'] * pricing['output'] * 1000000
        
        return {
            'input_tokens': self.usage['input_tokens'],
            'output_tokens': self.usage['output_tokens'],
            'cache_hits': self.usage['cache_hits'],
            'cache_misses': self.usage['cache_misses'],
            'input_cost': input_cost,
            'output_cost': output_cost,
            'total_cost': self.total_cost,
            'budget': self.budget,
            'budget_remaining': self.budget - self.total_cost,
            'is_discount_period': 16.5 <= datetime.now(timezone.utc).hour < 24 or 0 <= datetime.now(timezone.utc).hour < 0.5
        }

    def reset(self):
        """Reset usage statistics"""
        self.usage = {
            'input_tokens': 0,
            'output_tokens': 0,
            'cache_hits': 0,
            'cache_misses': 0
        }
        self.total_cost = 0.0

# Initialize cost tracker
cost_tracker = CostTracker()
