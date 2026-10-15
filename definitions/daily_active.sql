SELECT business_date, province, COUNT(DISTINCT user_id)::BIGINT AS active_users
FROM events
WHERE business_date = $business_date
GROUP BY business_date, province
ORDER BY province
