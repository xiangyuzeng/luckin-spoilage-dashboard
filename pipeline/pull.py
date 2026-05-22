"""pipeline/pull.py — refresh cache/ from SCM source-of-truth (TODO).

This is a STUB. To make daily auto-refresh actually pick up new data, implement
the queries below against luckyus_scm_shopstock.t_shop_spec_stock_change_record
and write the results to cache/spec_<spec_mid>.csv in the format expected by
build_v2.py.

Implementation paths (pick one):

  A) Direct MySQL via pymysql + AWS Secrets Manager (the luckin-ops-dashboard
     pattern). Requires the cron box to have IAM permission to GetSecretValue
     and the credentials secret name (e.g. luckyus/scm-shopstock/readonly).

  B) Call the on-prem mcp-db-gateway at http://10.238.3.43:8080 over HTTP.
     Requires figuring out the gateway's non-SSE query endpoint.

  C) Run this script inside a scheduled Claude Code agent (see /schedule skill)
     so the MCP tools are available; the agent writes the cache files and
     commits via /push-report.

For each spec_mid in ("GS07788-01", "GS07786-01", "GS07785-01", "GS07786-02"):

  SELECT spec_mid, operator_dept_id, operator_dept_name, operator_name,
         total_adjust_num, operated_time
  FROM   luckyus_scm_shopstock.t_shop_spec_stock_change_record
  WHERE  tenant = 'LKUS'
    AND  specific_reason_code = '015'
    AND  spec_mid = <spec_mid>
  ORDER BY operated_time;

Sales reference (also needs refresh — currently hardcoded in build_v2.py):

  SELECT shop_id, DATE_FORMAT(local_begin_date, '%Y-%m') AS month,
         SUM(total_order_quantity) AS orders
  FROM   luckyus_sales_order.t_order_store_fact
  WHERE  tenant = 'LKUS' AND cycle_type = 3
    AND  local_begin_date >= '2025-07-01'
  GROUP BY shop_id, month
  ORDER BY shop_id, month;

Once implemented, refresh.sh step 1 should call this script and bail on non-zero
exit. Until then, the cache directory is bootstrapped from a Claude Code session
and the cron will keep re-publishing the same data daily.
"""
import sys
print("ERROR: pipeline/pull.py is not yet implemented — see docstring for paths.",
      file=sys.stderr)
sys.exit(2)
