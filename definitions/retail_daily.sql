SELECT business_date, country,
       SUM(CASE WHEN line_type='sale' THEN amount_pence::BIGINT ELSE 0 END)::BIGINT AS gross_sales_pence,
       SUM(CASE WHEN line_type='refund' THEN amount_pence::BIGINT ELSE 0 END)::BIGINT AS refund_pence,
       SUM(CASE WHEN line_type='sale' THEN amount_pence::BIGINT ELSE -amount_pence::BIGINT END)::BIGINT AS net_sales_pence,
       SUM(CASE WHEN line_type='sale' THEN 1 ELSE 0 END)::BIGINT AS sale_lines,
       SUM(CASE WHEN line_type='refund' THEN 1 ELSE 0 END)::BIGINT AS refund_lines
FROM invoice_lines
WHERE business_date=$business_date
GROUP BY business_date,country
ORDER BY country
