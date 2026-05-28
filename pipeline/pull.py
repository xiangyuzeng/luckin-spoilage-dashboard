"""pipeline/pull.py — refresh cache/raw/batch_*.json + cache/spec_metadata.json from SCM.

The 2026-05 expansion changed this file from a stub to a runbook. It is designed
to be executed from a Claude Code session that has the mcp-db-gateway MCP server
attached (the workstation default). The mcp-db-gateway gives `mysql_query` access
to all luckyus_* databases; this script prints the exact queries to run.

Why not pure-Python pymysql? Because the on-prem MySQL gateway sits behind the
office VPN and we have not yet onboarded a Secrets Manager entry for the read
credential. Adding that is left to a future change; the cron job that calls this
script today is **not** unattended — it's the Claude Code session described in
docs/runbooks/spoilage_refresh.md.

USAGE (from a Claude Code session):

    1. List all SKUs we track:
         from pipeline.sku_catalog import SKU_CATALOG
         all_skus = list(SKU_CATALOG.keys())

    2. Pull spec metadata (cost + ratios + unit) for every SKU.
       Run these two queries via the mcp-db-gateway mysql_query tool:

         A) -- ratios + unit --
            SELECT mid, name, use_unit_mid, dly_use_ratio, cg_dly_ratio, status
            FROM   luckyus_scm_shopstock.t_mdm_goods_spec
            WHERE  tenant='LKUS' AND mid IN (<all_skus>);

         B) -- weighted-avg cost since 2025-01-01 --
            SELECT spec_mid,
                   ROUND(AVG(COALESCE(adjust_spec_cost_amount, spec_cost_amount)), 4)
                     AS avg_cost,
                   COUNT(*) AS receipts, MAX(receive_time) AS last_receive
            FROM   luckyus_scm_purchase.t_goods_spec_cost_detail
            WHERE  tenant='LKUS' AND spec_mid IN (<all_skus>)
              AND  receive_time >= '2025-01-01'
            GROUP  BY spec_mid;

       Join A + B by spec_mid and write to cache/spec_metadata.json (see
       existing file for schema).

    3. Pull spoilage records. To stay under the MCP gateway's response cap,
       split the SKU list into batches of ~4 large SKUs (>1000 rows each) and
       1 batch for all the smaller tails. Run:

         SELECT spec_mid, operator_dept_id, operator_dept_name, operator_name,
                total_adjust_num, operated_time
         FROM   luckyus_scm_shopstock.t_shop_spec_stock_change_record
         WHERE  tenant='LKUS' AND specific_reason_code='015'
           AND  spec_mid IN (<batch>)
         ORDER  BY spec_mid, operated_time;

       Each batched response will be saved to a tool-result file by the gateway.
       Copy those files to cache/raw/batch_NN.json (build_v2.py reads every
       cache/raw/batch_*.json glob).

    4. Re-run build pipeline:
         python3 pipeline/build_v2.py
         python3 pipeline/build_dashboard.py

Sales reference (currently hardcoded as SALES in build_v2.py) is independent —
update it via:

    SELECT shop_id, DATE_FORMAT(local_begin_date, '%Y-%m') AS month,
           SUM(total_order_quantity) AS orders
    FROM   luckyus_sales_order.t_order_store_fact
    WHERE  tenant='LKUS' AND cycle_type=3 AND local_begin_date >= '2025-07-01'
    GROUP  BY shop_id, month
    ORDER  BY shop_id, month;

FUTURE: When the read credential is in AWS Secrets Manager, replace step 2 + 3
with a pymysql client that writes the same cache files. The build pipeline does
not need to change.
"""
import sys
print("pipeline/pull.py is a runbook, not an executable. Read the docstring.",
      file=sys.stderr)
print("Run the documented queries from a Claude Code session with mcp-db-gateway attached.",
      file=sys.stderr)
sys.exit(2)
