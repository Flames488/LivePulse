-- Unique prediction per round per user
ALTER TABLE predictions
ADD CONSTRAINT unique_user_round UNIQUE (user_id, prediction_round_id);

-- Event deduplication per provider
ALTER TABLE match_events
ADD CONSTRAINT unique_event_provider UNIQUE (external_event_id, provider);

-- Composite leaderboard index
CREATE INDEX idx_leaderboard_score
ON user_scores (total_score DESC, updated_at DESC);
