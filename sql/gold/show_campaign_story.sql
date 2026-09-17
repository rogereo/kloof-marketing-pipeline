WITH campaign_summary AS (
  SELECT
    platform,
    campaign_id,
    ANY_VALUE(campaign_name) AS campaign_name,
    SUM(spend_zar) AS spend_zar,
    SUM(claimed_revenue_zar) AS claimed_revenue_zar,
    SUM(real_revenue_zar) AS real_revenue_zar,
    SUM(first_order_revenue_zar) AS first_order_revenue_zar,
    SUM(predicted_value_90d) AS predicted_value_90d,
    SAFE_DIVIDE(SUM(claimed_revenue_zar), SUM(spend_zar)) AS platform_roas,
    SAFE_DIVIDE(SUM(real_revenue_zar), SUM(spend_zar)) AS actual_roas,
    SAFE_DIVIDE(
      SUM(first_order_revenue_zar) + SUM(predicted_value_90d),
      SUM(spend_zar)
    ) AS value_adjusted_roas
  FROM `kloof-marketing-pipeline.kloof_gold.mart_campaign_value`
  GROUP BY platform, campaign_id
)

SELECT
  *,
  DENSE_RANK() OVER (ORDER BY platform_roas DESC) AS platform_roas_rank,
  DENSE_RANK() OVER (ORDER BY value_adjusted_roas DESC) AS value_adjusted_roas_rank
FROM campaign_summary
ORDER BY value_adjusted_roas_rank, campaign_name;
