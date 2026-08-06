# 🥬 Veggie Order Forecaster

Streamlit app that suggests how much of each vegetable/fruit to order,
following the store's weekly Basic/Full order cycle.

## Order cycle (as given by the store manager)

| Day       | Order type |
|-----------|-----------|
| Monday    | Full (Basic + Other veggies + Fruits) |
| Tuesday   | No order |
| Wednesday | Basic |
| Thursday  | Basic |
| Friday    | Full |
| Saturday  | Basic |
| Sunday    | No order *(assumed - wasn't specified; change in `item_config.py` if wrong)* |

**Basic order items:** Bindi/Okra, Green Chilli, Coriander, Mint, Lauki,
Drumstick, Tindoora, Arbi, Small Onion, Amla, Brinjal Purple, Brinjal
Green, Gwar, Karela, Paneer, Papdi.

**Full order** = Basic items + **Other veggies** (Methi, Toria/Turia,
Parwal, Ashgourd, Vellarikai, Puja Coconut, Ginger, Garlic, Green
Banana, Green Mango, Matoki, Pan Leaves, Suran, Long Beans) +
**Fruits** (Guava, Chikoo, Custard Apple, Alphonso Mango, Kesar Mango,
Banganpally Mango).

**Units:** Coriander and Mint are counted by **box** (e.g. 10 stk, 20
stk). Every other item is counted by **weight (kg)**.

The four-step math, run for every item on the selected order day:

1. When veggies are received, log the quantity (by weight, or box for
   coriander/mint).
2. Log wastage the same way.
3. `current_stock = last_received_qty - (sales + wastage since that receipt)`
4. `suggested_order_qty = previous week's sales for the day(s) this
   order needs to cover - current_stock`

"The day(s) this order needs to cover" isn't always just one day - e.g.
a Monday Full order has to last through Tuesday too (no order that
day), and Friday's Full order for **Other/Fruit items only** has to
last through Saturday and Sunday since those items aren't reordered
again until the next Monday. This is computed automatically in
`item_config.coverage_weekdays()` from the calendar above - you don't
need to hardcode it per item.

## File structure

```
streamlit_app.py       # Main app - entry point for Streamlit Cloud
item_config.py          # Item master list (category + unit) + order calendar
forecast_engine.py      # Core forecasting math (steps 1-4 above)
inventory_log.py        # Append/read helpers for the receiving & wastage logs
forecast_orders.py      # CLI version, if you want to run this outside the app
requirements.txt        # streamlit, pandas
data/
  item_master.csv        # item, category, unit, shelf_life_days, safety_buffer_pct
  sample_sales_history.csv  # 4 weeks of demo sales data (date, item, qty_sold)
  receiving_log.csv       # date, item, received_qty (starts empty)
  wastage_log.csv         # date, item, wastage_qty (starts empty)
```

## What changed from the previous version

- `item_config.py` and `forecast_engine.py` are new - the previous
  `streamlit_app.py` already imported them but they weren't present in
  the repo you shared, so the app couldn't have been running as-is.
- The order formula changed from "7-day weighted average x shelf-life
  horizon x safety buffer" (the old `forecast_orders.py` /
  `veggie_forecaster.ipynb` logic) to "previous week's sales for the
  covered day(s) minus current stock," per your manager's spec. The
  safety buffer is now **off by default** (there's a checkbox in the
  sidebar to turn it back on) since the manager's formula doesn't call
  for one.
- Added two new tabs in the app: **Log Receiving** and **Log Wastage**,
  which write to `data/receiving_log.csv` / `data/wastage_log.csv`.
  Current stock is then auto-computed from those logs, with a manual
  override still available for items you haven't started logging yet.
- `requirements.txt` was missing `pandas`, which both `forecast_orders.py`
  and `streamlit_app.py` need - added.
- `shelf_life.csv` is replaced by `data/item_master.csv`, which adds
  the `category` (basic/other/fruit) and `unit` (kg/box) columns needed
  for the new calendar logic, alongside the same shelf-life/buffer
  columns as before (still there for reference / the optional buffer).
- `veggie_forecaster.ipynb` (the exploratory notebook) wasn't touched -
  it's not part of the deployed app and still reflects the old model.
  Happy to update it too if you still use it for exploration.

## Running locally

```
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Deploying (Streamlit Community Cloud)

1. Push this whole folder to GitHub, with `streamlit_app.py` at the repo root.
2. https://share.streamlit.io -> New app -> pick the repo/branch.
3. Main file path: `streamlit_app.py`.
4. Make sure `requirements.txt` is committed.

Because Streamlit Cloud's filesystem is ephemeral on redeploys, the
`data/receiving_log.csv` / `wastage_log.csv` logs will reset if the app
redeploys or restarts. For a single shop this is usually fine short
term, but if you want the logs to survive restarts long-term, swap
`inventory_log.py` to write to a small hosted database (e.g. Google
Sheets, Supabase, or SQLite on a persistent volume) instead of local
CSVs - the rest of the app doesn't need to change, since it only talks
to `inventory_log.py`'s two functions.

## Adjusting things later

- **Change which items are basic/full/fruit, or their units:** edit
  `ITEMS` in `item_config.py`, then re-derive `data/item_master.csv`
  (or just edit that CSV directly - the app reads it for display/buffer
  purposes only, `item_config.py` is what actually drives order scope).
- **Change the order calendar:** edit `ORDER_CALENDAR` in `item_config.py`.
- **Confirm/fix the Sunday assumption:** see the table above.
