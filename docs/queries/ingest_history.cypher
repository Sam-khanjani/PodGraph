// Ingestion audit trail, latest first (one IngestRun node per pipeline run)
MATCH (r:IngestRun)
RETURN r.run_at AS at, r.episode_id AS episode, r.status AS status, r.chunks AS chunks, r.reason AS reason
ORDER BY r.run_at DESC LIMIT 20;
