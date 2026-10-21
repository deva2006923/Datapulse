import math
from typing import Optional

# Configurable bounds for dataset unlock pricing
MIN_UNLOCK_PRICE = 5
MAX_UNLOCK_PRICE = 50

def calculate_dataset_unlock_price(
    quality_score: float,
    completeness_score: float,
    domain_relevance_score: float,
    rows_count: int,
    columns_count: int
) -> int:
    """
    Calculates a deterministic, transparent, and bounded unlock price in credits.

    Factors:
      - Base price: 5 credits
      - Quality component: up to 15 credits (0.15 * quality_score)
      - Completeness component: up to 10 credits (0.10 * completeness_score)
      - Domain relevance component: up to 5 credits (0.05 * domain_relevance_score)
      - Volume & complexity component: up to 15 credits
          * Row logarithmic scale: up to 12 credits (3.5 * log10(rows))
          * Column complexity: up to 8 credits (0.5 * cols)
          * Combined volume capped at 15 credits
      - Total price clamped to [MIN_UNLOCK_PRICE, MAX_UNLOCK_PRICE] (5 to 50 credits)
    """
    q_score = max(0.0, min(100.0, float(quality_score)))
    c_score = max(0.0, min(100.0, float(completeness_score)))
    d_score = max(0.0, min(100.0, float(domain_relevance_score)))

    q_pts = (q_score / 100.0) * 15.0
    c_pts = (c_score / 100.0) * 10.0
    d_pts = (d_score / 100.0) * 5.0

    # Logarithmic scaling on rows to handle wide row variations gracefully
    safe_rows = max(1, rows_count)
    row_pts = min(12.0, math.log10(safe_rows) * 3.5)

    # Linear scaling on columns bounded at 8 pts
    safe_cols = max(0, columns_count)
    col_pts = min(8.0, safe_cols * 0.5)

    volume_pts = min(15.0, row_pts + col_pts)

    raw_price = 5.0 + q_pts + c_pts + d_pts + volume_pts
    price = int(round(raw_price))

    return max(MIN_UNLOCK_PRICE, min(MAX_UNLOCK_PRICE, price))
