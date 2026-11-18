-- One ready-to-post copy pack per clip (titles, description, hashtags, tags, research).
-- Written by services/post_pack_service.py. Regenerating replaces the row.
-- (No semicolons in comments: database.py splits migration files on them.)
CREATE TABLE IF NOT EXISTS clip_post_packs (
    clip_id VARCHAR(36) PRIMARY KEY REFERENCES generated_clips(id) ON DELETE CASCADE,
    task_id VARCHAR(36) NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    pack JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_clip_post_packs_task ON clip_post_packs (task_id);
