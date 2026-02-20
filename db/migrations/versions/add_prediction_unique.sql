CREATE UNIQUE INDEX IF NOT EXISTS uniq_prediction
ON predictions(user_id, round_id);
