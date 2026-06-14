"""
Generates 20,000 synthetic rows for the k8s_ops schema and writes
the full 003_seed_k8s_ops.sql file.

Distribution:
  clusters     :    50
  nodes        :   500
  deployments  :   500
  pods         : 10,000
  incidents    :  1,500
  alerts       :  5,000
  oncall_logs  :  2,500
               -------
  Total        : 20,050
"""

import random
from datetime import datetime, timedelta

#fix the random seed so the generated data is the same every time you run this
random.seed(42)

# ── helpers ─────────────────────────────────────────────────────────────────

#picks a random timestamp between start and end and returns it as a sql-formatted string
def rand_ts(start: datetime, end: datetime) -> str:
    delta = end - start
    secs  = int(delta.total_seconds())
    t     = start + timedelta(seconds=random.randint(0, secs))
    return t.strftime("'%Y-%m-%d %H:%M:%S+00'")

#all generated timestamps will fall within this 2-year window
START = datetime(2024, 1, 1)
END   = datetime(2026, 6, 1)

# ── lookup tables ────────────────────────────────────────────────────────────

#all the possible values we randomly pick from when generating each row
REGIONS = [
    "us-east-1","us-west-2","eu-west-1","eu-central-1",
    "ap-southeast-1","ap-northeast-1","ca-central-1","sa-east-1",
]
ENVIRONMENTS = ["production","staging","development","qa","uat"]
K8S_VERSIONS = ["1.27.12","1.28.8","1.29.4","1.30.1","1.31.0"]

# instance type → (cpu_cores, memory_gb)
NODE_TYPES = {
    "t3.xlarge"  : (4,  16),
    "t3.2xlarge" : (8,  32),
    "m5.xlarge"  : (4,  16),
    "m5.2xlarge" : (8,  32),
    "m5.4xlarge" : (16, 64),
    "c5.xlarge"  : (4,   8),
    "c5.2xlarge" : (8,  16),
    "c5.4xlarge" : (16, 32),
    "r5.xlarge"  : (4,  32),
    "r5.2xlarge" : (8,  64),
    "r5.4xlarge" : (16,128),
    "g4dn.xlarge": (4,  16),
    "g4dn.2xlarge":(8,  32),
}
NODE_TYPE_LIST   = list(NODE_TYPES.keys())
#most nodes are Ready — only a small fraction are unhealthy to make data realistic
NODE_STATUSES    = ["Ready","Ready","Ready","Ready","NotReady","SchedulingDisabled"]

NAMESPACES = [
    "default","kube-system","monitoring","logging","ingress-nginx",
    "cert-manager","data-pipeline","ml-serving","auth","payments",
    "search","recommendations","notifications","analytics","gateway",
]

IMAGES = [
    "nginx","redis","postgres","mongodb","rabbitmq","kafka",
    "elasticsearch","kibana","grafana","prometheus","jaeger",
    "envoy","fluentd","vector","loki","tempo","minio",
    "pytorch/pytorch","tensorflow/tensorflow","python",
]

SERVICES = [
    "api-gateway","user-service","order-service","payment-service",
    "inventory-service","notification-service","auth-service","search-service",
    "recommendation-engine","analytics-worker","log-aggregator","metric-collector",
    "cache-warmer","job-scheduler","data-exporter","config-sync",
    "audit-logger","rate-limiter","feature-flag-service","health-checker",
]

SEVERITIES = ["critical","high","medium","low"]
ALERT_NAMES = [
    "PodCrashLooping","NodeNotReady","HighCPUUsage","HighMemoryUsage",
    "DiskPressure","NetworkLatencyHigh","PVCNearlyFull","DeploymentReplicasMismatch",
    "ContainerOOMKilled","EndpointDown","CertificateExpiringSoon","EtcdHighCommitDuration",
    "KubeletTooManyPods","SchedulerDown","APIServerLatencyHigh","NodeDiskPressure",
    "PodNotScheduled","HPA_MaxedOut","PersistentVolumeError","ServiceAccountTokenExpired",
]
ALERT_SEVERITIES = ["INFO","WARN","CRIT","HIGH"]

#template strings for realistic-looking root cause analysis summaries
RCA_TEMPLATES = [
    "Memory leak in {svc} caused OOM kill; fix: increased limits and patched v{ver}.",
    "Network partition between zones led to split-brain; fix: updated topology spread constraints.",
    "Misconfigured HPA caused thrashing; fix: adjusted stabilization window to 300s.",
    "Certificate expired for {svc}; fix: rotated cert and added renewal alert.",
    "Disk I/O saturation on node due to log accumulation; fix: log rotation policy applied.",
    "Faulty node {node} triggered pod eviction storm; fix: cordoned node and drained workloads.",
    "Etcd compaction lag caused API server timeouts; fix: tuned compaction interval.",
    "Image pull rate-limited by registry; fix: switched to internal mirror.",
    "ConfigMap hot-reload bug in {svc} v{ver}; fix: pinned to stable version.",
    "DNS resolution failure under load; fix: scaled CoreDNS replicas from 2 to 5.",
]

ENGINEERS = [
    "alice.johnson","bob.smith","carol.white","dave.lee","eva.garcia",
    "frank.patel","grace.kim","henry.nguyen","iris.chen","jack.wilson",
    "karen.martinez","liam.brown","mia.taylor","noah.davis","olivia.jones",
    "peter.miller","quinn.anderson","rose.thomas","sam.jackson","tina.moore",
]

#generates a random rca summary string by filling in a template with random service/version/node names
def rca(svc_list: list) -> str:
    tpl = random.choice(RCA_TEMPLATES)
    return tpl.format(
        svc  = random.choice(svc_list),
        ver  = f"{random.randint(1,5)}.{random.randint(0,20)}.{random.randint(0,9)}",
        node = f"node-{random.randint(100,999)}",
    ).replace("'", "''")  #escape single quotes so the sql string doesnt break

#generates a random semver-style version string like "3.14.2"
def version() -> str:
    return f"{random.randint(1,5)}.{random.randint(0,30)}.{random.randint(0,9)}"

# ── generate data ────────────────────────────────────────────────────────────

NUM_CLUSTERS     =    50
NUM_NODES        =   500
NUM_DEPLOYMENTS  =   500
NUM_PODS         = 10_000
NUM_INCIDENTS    =  1_500
NUM_ALERTS       =  5_000
NUM_ONCALL       =  2_500

#generate cluster rows — each cluster has a unique name built from env + region + index
clusters = []
used_names: set = set()
for i in range(1, NUM_CLUSTERS + 1):
    env    = random.choice(ENVIRONMENTS)
    region = random.choice(REGIONS)
    short  = region.replace("-","")
    base   = f"{env}-{short}-{i:03d}"
    name   = base
    j = 2
    #if the name already exists, keep appending a counter until its unique
    while name in used_names:
        name = f"{base}-{j}"; j += 1
    used_names.add(name)
    clusters.append((
        i, name, region, env,
        random.choice(K8S_VERSIONS),
        rand_ts(START, END),
    ))

#generate node rows — each node belongs to a random cluster
nodes = []
for i in range(1, NUM_NODES + 1):
    nt         = random.choice(NODE_TYPE_LIST)
    cpu, mem   = NODE_TYPES[nt]
    cluster_id = random.randint(1, NUM_CLUSTERS)
    nodes.append((
        i, cluster_id, nt, cpu, mem,
        random.choice(NODE_STATUSES),
        rand_ts(START, END),
    ))

#generate deployment rows — each deployment belongs to a random cluster and namespace
deployments = []
svc_pool = SERVICES * (NUM_DEPLOYMENTS // len(SERVICES) + 1)
random.shuffle(svc_pool)
for i in range(1, NUM_DEPLOYMENTS + 1):
    svc_name   = svc_pool[i - 1]
    cluster_id = random.randint(1, NUM_CLUSTERS)
    ns         = random.choice(NAMESPACES)
    image      = f"{random.choice(IMAGES)}:{version()}"
    deployments.append((
        i, svc_name, ns,
        random.choice([1, 2, 3, 4, 5, 6, 8, 10]),
        image, version(), cluster_id,
        rand_ts(START, END),
    ))

#generate pod rows — each pod belongs to a deployment and runs on a random node
pod_statuses = ["Running","Running","Running","Pending","Failed","Succeeded","CrashLoopBackOff","Evicted"]
pods = []
for i in range(1, NUM_PODS + 1):
    dep_id  = random.randint(1, NUM_DEPLOYMENTS)
    node_id = random.randint(1, NUM_NODES)
    #inherit the namespace from the deployment this pod belongs to
    ns      = deployments[dep_id - 1][2]
    pods.append((
        i, ns, dep_id,
        random.choice(pod_statuses),
        node_id,
        rand_ts(START, END),
    ))

#generate incident rows — mttr is how many minutes it took to resolve the incident
incidents = []
svc_names_flat = [d[1] for d in deployments]
for i in range(1, NUM_INCIDENTS + 1):
    cluster_id  = random.randint(1, NUM_CLUSTERS)
    sev         = random.choice(SEVERITIES)
    started     = START + timedelta(seconds=random.randint(0, int((END - START).total_seconds())))
    resolved    = started + timedelta(minutes=random.randint(5, 2880))
    mttr        = int((resolved - started).total_seconds() // 60)
    incidents.append((
        i, sev, cluster_id,
        started.strftime("'%Y-%m-%d %H:%M:%S+00'"),
        resolved.strftime("'%Y-%m-%d %H:%M:%S+00'"),
        mttr,
        rca(svc_names_flat),
    ))

#generate alert rows — each alert is fired by a specific pod
alerts = []
for i in range(1, NUM_ALERTS + 1):
    pod_id   = random.randint(1, NUM_PODS)
    fired_at = rand_ts(START, END)
    alerts.append((
        i, fired_at,
        random.choice(ALERT_SEVERITIES),
        pod_id,
        random.choice(ALERT_NAMES),
        random.choice(["TRUE","FALSE","FALSE","FALSE"]),  #most alerts are not resolved
    ))

#generate oncall log rows — each log entry records who was paged and how fast they responded
oncall_logs = []
for i in range(1, NUM_ONCALL + 1):
    incident_id   = random.randint(1, NUM_INCIDENTS)
    paged_at      = rand_ts(START, END)
    response_time = random.randint(1, 120)
    oncall_logs.append((
        i,
        random.choice(ENGINEERS),
        paged_at,
        incident_id,
        response_time,
    ))

# ── render SQL ───────────────────────────────────────────────────────────────

CHUNK = 500  # rows per VALUES block — keeps each insert statement a manageable size

#helper that splits a list into chunks of size n
def chunked(lst, n):
    for k in range(0, len(lst), n):
        yield lst[k:k+n]

#build the sql file as a list of strings then join them at the end
lines = []
W = lines.append

W("""-- ============================================================
--  003_seed_k8s_ops.sql  –  20,050 synthetic rows
--  Generated by seed/generate_seed.py
-- ============================================================

DROP TABLE IF EXISTS oncall_logs  CASCADE;
DROP TABLE IF EXISTS alerts       CASCADE;
DROP TABLE IF EXISTS pods         CASCADE;
DROP TABLE IF EXISTS incidents    CASCADE;
DROP TABLE IF EXISTS deployments  CASCADE;
DROP TABLE IF EXISTS nodes        CASCADE;
DROP TABLE IF EXISTS clusters     CASCADE;


-- ────────────────────────────────────────────────────────────
--  SCHEMA
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS clusters (
    cluster_id   SERIAL PRIMARY KEY,
    name         VARCHAR(128) UNIQUE NOT NULL,
    region       VARCHAR(64)  NOT NULL,
    envornment   VARCHAR(32)  NOT NULL,
    k8s_version  VARCHAR(16)  NOT NULL,
    created_at   TIMESTAMP    NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS nodes (
    node_id      SERIAL PRIMARY KEY,
    cluster_id   INTEGER  NOT NULL REFERENCES clusters(cluster_id) ON DELETE CASCADE,
    node_type    VARCHAR(32) NOT NULL,
    cpu_cores    SMALLINT    NOT NULL,
    memory_gb    SMALLINT    NOT NULL,
    status       VARCHAR(32) NOT NULL DEFAULT 'Ready',
    created_at   TIMESTAMP   NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS deployments (
    deployment_id SERIAL PRIMARY KEY,
    name          VARCHAR(128) NOT NULL,
    namespace     VARCHAR(64)  NOT NULL,
    replicas      INTEGER      NOT NULL DEFAULT 1,
    image         VARCHAR(255) NOT NULL,
    version       VARCHAR(32)  NOT NULL,
    cluster_id    INTEGER      NOT NULL REFERENCES clusters(cluster_id),
    created_at    TIMESTAMP    NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pods (
    pod_id        SERIAL PRIMARY KEY,
    namespace     VARCHAR(64) NOT NULL,
    deployment_id INTEGER     NOT NULL REFERENCES deployments(deployment_id),
    status        VARCHAR(32) NOT NULL DEFAULT 'Running',
    node_id       INTEGER     NOT NULL REFERENCES nodes(node_id),
    created_at    TIMESTAMP   NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS incidents (
    incident_id   SERIAL PRIMARY KEY,
    severity      VARCHAR(16) NOT NULL,
    cluster_id    INTEGER     NOT NULL REFERENCES clusters(cluster_id),
    started_at    TIMESTAMP   NOT NULL,
    resolved_at   TIMESTAMP,
    mttr_minutes  INTEGER,
    rca_summary   TEXT
);

CREATE TABLE IF NOT EXISTS alerts (
    alert_id      SERIAL PRIMARY KEY,
    fired_at      TIMESTAMP   NOT NULL,
    severity      VARCHAR(4)  NOT NULL,
    source_pod_id INTEGER     NOT NULL REFERENCES pods(pod_id),
    alertname     VARCHAR(128) NOT NULL,
    resolved      BOOLEAN     NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS oncall_logs (
    log_id             SERIAL PRIMARY KEY,
    engineer           VARCHAR(128) NOT NULL,
    paged_at           TIMESTAMP    NOT NULL,
    incident_id        INTEGER      NOT NULL REFERENCES incidents(incident_id),
    response_time_mins INTEGER      NOT NULL
);


-- ────────────────────────────────────────────────────────────
--  INDEXES
-- ────────────────────────────────────────────────────────────

CREATE INDEX idx_nodes_cluster        ON nodes(cluster_id);
CREATE INDEX idx_deployments_cluster  ON deployments(cluster_id);
CREATE INDEX idx_pods_deployment      ON pods(deployment_id);
CREATE INDEX idx_pods_node            ON pods(node_id);
CREATE INDEX idx_pods_status          ON pods(status);
CREATE INDEX idx_incidents_cluster    ON incidents(cluster_id);
CREATE INDEX idx_incidents_severity   ON incidents(severity);
CREATE INDEX idx_alerts_fired_at      ON alerts(fired_at);
CREATE INDEX idx_alerts_severity      ON alerts(severity);
CREATE INDEX idx_oncall_incident      ON oncall_logs(incident_id);


-- ════════════════════════════════════════════════════════════
--  DATA
-- ════════════════════════════════════════════════════════════

-- clusters (50 rows)
""")

#write each table's data in chunks of 500 rows per INSERT statement
for chunk in chunked(clusters, CHUNK):
    W("INSERT INTO clusters (cluster_id, name, region, envornment, k8s_version, created_at) VALUES")
    rows = []
    for r in chunk:
        rows.append(f"  ({r[0]}, '{r[1]}', '{r[2]}', '{r[3]}', '{r[4]}', {r[5]})")
    W(",\n".join(rows) + ";")
    W("")

W("-- nodes (500 rows)")
for chunk in chunked(nodes, CHUNK):
    W("INSERT INTO nodes (node_id, cluster_id, node_type, cpu_cores, memory_gb, status, created_at) VALUES")
    rows = []
    for r in chunk:
        rows.append(f"  ({r[0]}, {r[1]}, '{r[2]}', {r[3]}, {r[4]}, '{r[5]}', {r[6]})")
    W(",\n".join(rows) + ";")
    W("")

W("-- deployments (500 rows)")
for chunk in chunked(deployments, CHUNK):
    W("INSERT INTO deployments (deployment_id, name, namespace, replicas, image, version, cluster_id, created_at) VALUES")
    rows = []
    for r in chunk:
        rows.append(f"  ({r[0]}, '{r[1]}', '{r[2]}', {r[3]}, '{r[4]}', '{r[5]}', {r[6]}, {r[7]})")
    W(",\n".join(rows) + ";")
    W("")

W("-- pods (10,000 rows)")
for chunk in chunked(pods, CHUNK):
    W("INSERT INTO pods (pod_id, namespace, deployment_id, status, node_id, created_at) VALUES")
    rows = []
    for r in chunk:
        rows.append(f"  ({r[0]}, '{r[1]}', {r[2]}, '{r[3]}', {r[4]}, {r[5]})")
    W(",\n".join(rows) + ";")
    W("")

W("-- incidents (1,500 rows)")
for chunk in chunked(incidents, CHUNK):
    W("INSERT INTO incidents (incident_id, severity, cluster_id, started_at, resolved_at, mttr_minutes, rca_summary) VALUES")
    rows = []
    for r in chunk:
        rows.append(f"  ({r[0]}, '{r[1]}', {r[2]}, {r[3]}, {r[4]}, {r[5]}, '{r[6]}')")
    W(",\n".join(rows) + ";")
    W("")

W("-- alerts (5,000 rows)")
for chunk in chunked(alerts, CHUNK):
    W("INSERT INTO alerts (alert_id, fired_at, severity, source_pod_id, alertname, resolved) VALUES")
    rows = []
    for r in chunk:
        rows.append(f"  ({r[0]}, {r[1]}, '{r[2]}', {r[3]}, '{r[4]}', {r[5]})")
    W(",\n".join(rows) + ";")
    W("")

W("-- oncall_logs (2,500 rows)")
for chunk in chunked(oncall_logs, CHUNK):
    W("INSERT INTO oncall_logs (log_id, engineer, paged_at, incident_id, response_time_mins) VALUES")
    rows = []
    for r in chunk:
        rows.append(f"  ({r[0]}, '{r[1]}', {r[2]}, {r[3]}, {r[4]})")
    W(",\n".join(rows) + ";")
    W("")

#join all the sql strings into one big file and write it to disk
sql = "\n".join(lines)

out_path = "seed/migrations/003_seed_k8s_ops.sql"
with open(out_path, "w", encoding="utf-8") as f:
    f.write(sql)

total = (len(clusters) + len(nodes) + len(deployments) +
         len(pods) + len(incidents) + len(alerts) + len(oncall_logs))
print(f"Written {total:,} rows to {out_path}")
print(f"  clusters     : {len(clusters):>6,}")
print(f"  nodes        : {len(nodes):>6,}")
print(f"  deployments  : {len(deployments):>6,}")
print(f"  pods         : {len(pods):>6,}")
print(f"  incidents    : {len(incidents):>6,}")
print(f"  alerts       : {len(alerts):>6,}")
print(f"  oncall_logs  : {len(oncall_logs):>6,}")
