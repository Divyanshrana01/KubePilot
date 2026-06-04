DROP TABLE IF EXISTS oncall_logs     CASCADE;
DROP TABLE IF EXISTS alerts          CASCADE;
DROP TABLE IF EXISTS pods            CASCADE;
DROP TABLE IF EXISTS incidents       CASCADE;
DROP TABLE IF EXISTS nodes           CASCADE;
DROP TABLE IF EXISTS clusters        CASCADE;


CREATE TABLE IF NOT EXISTS clusters (
    cluster_id            SERIAL PRIMARY KEY,
    name                  VARCHAR(128) UNIQUE NOT NULL,
    region                VARCHAR(64) NOT NULL,
    envornment            VARCHAR(32) NOT NULL,
    k8s_version           VARCHAR(16) NOT NULL,
    created_at            TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS nodes (
    node_id               SERIAL PRIMARY KEY,
    cluster_id            INTEGER NOT NULL REFERENCES clusters(cluster_id) ON DELETE CASCADE,
    node_type             VARCHAR(32) NOT NULL,
    cpu_cores             SMALLINT NOT NULL,
    memory_gb             SMALLINT NOT NULL,
    status                VARCHAR(32) NOT NULL DEFAULT 'Ready',
    created_at            TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS deployments(
    deployment_id         SERIAL PRIMARY KEY,
    name                  VARCHAR(128) NOT NULL,
    namespace             VARCHAR(64) NOT NULL,
    replicas              INTEGER NOT NULL DEFAULT 1,
    image                 VARCHAR(255) NOT NULL,
    version               VARCHAR(32) NOT NULL,
    cluster_id            INTEGER NOT NULL REFERENCES clusters(cluster_id),
    created_at            TIMESTAMP NOT NULL DEFAULT now()
)

CREATE TABLE IF NOT EXISTS pods (
    pod_id                SERIAL PRIMARY KEY,
    namespace             VARCHAR(64) NOT NULL,
    deployment_id         INTEGER NOT NULL REFERENCES deployments(deployment_id),
    status                VARCHAR(32) NOT NULL DEFAULT 'Running',
    node_id               INTEGER NOT NULL REFERENCES nodes(node_id),
    created_at            TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS incidents (
    incident_id           SERIAL PRIMARY KEY,
    severity              VARCHAR(16) NOT NULL,
    cluster_id            INTEGER NOT NULL REFERENCES clusters(cluster_id),
    started_at            TIMESTAMP NOT NULL,
    resolved_at           TIMESTAMP,
    mttr_minutes          INTEGER,
    rca_summary           TEXT,
);

CREATE TABLE IF NOT EXISTS alerts (
    alert_id              SERIAL PRIMARY KEY,
    fired_id              TIMESTAMP NOT NULL,
    security              VARCHAR(4) NOT NULL,
    source_pod_id         INTEGER NOT NULL REFERENCES pods(pod_id),
    alertname             VARCHAR(128) NOT NULL,
    resolved              BOOLEAN NOT NULL DEFAULT FALSE,
);


CREATE TABLE IF NOT EXISTS oncall_logs (
    log_id                SERIAL PRIMARY KEY,
    engineer              VARCHAR(128) NOT NULL,
    padeg_at              TIMESTAMP NOT NULL,
    incident_id           INTEGER NOT NULL REFERENCES incidents(incident_id),
    response_time_mins INTEGER NOT NULL,
);



CREATE INDEX idx_incidents_cluster             ON incidents(cluster_id);
CREATE INDEX idx_pods_deployment               ON pods(deployment_id);
CREATE INDEX idx_pods_node                     ON pods(node_id);
CREATE INDEX idx_pods_status                   ON pods(status);
CREATE INDEX idx_incidents_cluster             ON incidents(cluster_id);
CREATE INDEX idx_alert_fired_at                ON alerts(fired_at);
CREATE INDEX idx_alerts_severity               ON alerts(severity);
CREATE INDEX idx_oncall_incident               ON incidents(incident_id);



