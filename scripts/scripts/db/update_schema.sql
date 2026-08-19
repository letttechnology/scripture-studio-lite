-- Add github_issues and session_issues columns to ai_session_log table

ALTER TABLE ai_session_log ADD COLUMN github_issues TEXT;
ALTER TABLE ai_session_log ADD COLUMN session_issues TEXT;

-- Migrate existing data: split old 'issues' column
UPDATE ai_session_log
SET
  github_issues = CASE
    WHEN issues LIKE '#%' OR issues LIKE '%,#%' THEN issues
    ELSE NULL
  END,
  session_issues = CASE
    WHEN issues NOT LIKE '#%' AND issues NOT LIKE '%,#%' THEN issues
    ELSE NULL
  END
WHERE issues IS NOT NULL;
