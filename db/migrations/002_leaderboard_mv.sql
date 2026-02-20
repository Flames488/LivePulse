-- ==============================
-- Leaderboard materialized view
-- ==============================

create materialized view if not exists leaderboard_mv as
select
  user_id,
  sum(points) as total_points,
  count(*) filter (where correct = true) as correct_predictions,
  count(*) as total_predictions,
  case
    when count(*) = 0 then 0
    else round(
      (count(*) filter (where correct = true)::numeric / count(*)) * 100,
      2
    )
  end as accuracy_percentage
from user_scores
group by user_id;

create unique index if not exists idx_leaderboard_mv_user
  on leaderboard_mv(user_id);
