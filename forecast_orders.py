"""
Veggie Order Forecaster (CLI)
------------------------------
Command-line wrapper around forecast_engine.py, for generating an order
sheet without opening the Streamlit app - e.g. to run as a scheduled
script the morning of an order day.

This replaces the old trailing-7-day-weighted-average model. The order
math now follows the store manager's cycle (see item_config.py and
forecast_engine.py for the full explanation):

  1. current_stock = last received qty - (sales + wastage since then)
  2. order_qty      = previous week's sales for the day(s) this order
                       covers - current_stock

Usage:
  python3 forecast_orders.py <order_day> [sales_csv] [receiving_csv] [wastage_csv]

  order_day     e.g. Monday, Wednesday, Friday - must be a day in
                item_config.ORDER_CALENDAR that actually has an order
  sales_csv     default: data/sample_sales_history.csv
  receiving_csv default: data/receiving_log.csv (optional - skip logging
                by passing "" if you haven't started using it yet)
  wastage_csv   default: data/wastage_log.csv (optional, same as above)

Example:
  python3 forecast_orders.py Monday data/sample_sales_history.csv
"""

import sys

from forecast_engine import forecast_order
from item_config import order_days_available


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 forecast_orders.py <order_day> [sales_csv] [receiving_csv] [wastage_csv]")
        print(f"order_day must be one of: {', '.join(order_days_available())}")
        sys.exit(1)

    order_day = sys.argv[1]
    if order_day not in order_days_available():
        print(f"'{order_day}' has no order in item_config.ORDER_CALENDAR.")
        print(f"Choose one of: {', '.join(order_days_available())}")
        sys.exit(1)

    sales_csv = sys.argv[2] if len(sys.argv) > 2 else "data/sample_sales_history.csv"
    receiving_csv = sys.argv[3] if len(sys.argv) > 3 else "data/receiving_log.csv"
    wastage_csv = sys.argv[4] if len(sys.argv) > 4 else "data/wastage_log.csv"

    forecast = forecast_order(
        order_day,
        history_csv=sales_csv,
        receiving_csv=receiving_csv or None,
        wastage_csv=wastage_csv or None,
    )

    if forecast.empty:
        print(f"No items scheduled for {order_day}.")
        sys.exit(0)

    out_path = "order_recommendations.csv"
    forecast.to_csv(out_path, index=False)

    print(f"\n=== Order Recommendations for {order_day} ===\n")
    print(forecast.to_string(index=False))
    print(f"\nSaved to: {out_path}")


if __name__ == "__main__":
    main()
