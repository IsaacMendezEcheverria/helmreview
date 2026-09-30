from conftest import analyze_file, analyze_text, checks_for


def test_good_manifest_has_no_medium_or_high():
    rep = analyze_file("good.yaml")
    serious = [f for f in rep.findings if f.severity in ("HIGH", "MEDIUM")]
    assert serious == [], serious


def test_k8s_issues_detected():
    rep = analyze_file("k8s_issues.yaml")
    high = checks_for(rep, severity="HIGH")
    assert {"image-tag", "secret-en-env", "api-deprecada", "host-namespaces"} <= high
    assert "ingress-tls" in checks_for(rep, "Ingress/web")
    assert "pdb-bloqueo" in checks_for(rep, "StatefulSet/db")
    assert "replicas" in checks_for(rep, "StatefulSet/db")
    assert "replicas-hpa" in checks_for(rep, "Deployment/web")


def test_capacity_totals():
    rep = analyze_file("k8s_issues.yaml")
    cap = {c.resource: c for c in rep.capacity}
    web = cap["Deployment/web"]
    assert (web.replicas_base, web.replicas_max) == (3, 10)
    assert web.cpu_req_m == 250
    db = cap["StatefulSet/db"]
    assert db.cpu_req_m == 2000  # sin requests => request = limit
    assert cap["DaemonSet/agent"].per_node
    assert rep.storage[0].size_b == 50 * 2**30


def test_init_containers_use_max_not_sum():
    rep = analyze_text("""
apiVersion: apps/v1
kind: Deployment
metadata: {name: x}
spec:
  replicas: 2
  template:
    spec:
      initContainers:
      - {name: i1, image: a:1, resources: {requests: {cpu: 1, memory: 1Gi}, limits: {memory: 1Gi}}}
      - {name: i2, image: a:1, resources: {requests: {cpu: 500m, memory: 2Gi}, limits: {memory: 2Gi}}}
      containers:
      - {name: c, image: a:1, resources: {requests: {cpu: 200m, memory: 256Mi}, limits: {memory: 256Mi}}}
""")
    c = rep.capacity[0]
    assert c.cpu_req_m == 1000
    assert c.mem_req_b == 2 * 2**30


def test_invalid_resources_and_request_over_limit():
    rep = analyze_text("""
apiVersion: v1
kind: Pod
metadata: {name: p}
spec:
  containers:
  - {name: c, image: a:1, resources: {requests: {cpu: 2, memory: abc}, limits: {cpu: 1, memory: 1Gi}}}
""")
    msgs = [f.message for f in rep.findings]
    assert "resources-invalido" in checks_for(rep)
    assert any("requests.cpu" in m and "> limits.cpu" in m for m in msgs)


def test_rbac_and_service():
    rep = analyze_text("""
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata: {name: r}
rules: [{apiGroups: [""], resources: [secrets], verbs: [get, list]}, {apiGroups: ["*"], resources: ["*"], verbs: ["*"]}]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata: {name: b}
roleRef: {kind: ClusterRole, name: cluster-admin}
---
apiVersion: v1
kind: Service
metadata: {name: s}
spec: {type: NodePort, externalIPs: [1.2.3.4]}
""")
    assert {"rbac-secrets", "rbac-wildcard"} <= checks_for(rep, "ClusterRole/r")
    assert "rbac" in checks_for(rep, "ClusterRoleBinding/b", "HIGH")
    assert {"service-type", "service-externalips"} <= checks_for(rep, "Service/s")


def test_yaml_error_is_reported():
    rep = analyze_text("apiVersion: v1\nkind: ConfigMap\nmetadata: {name: [unclosed\n")
    assert "yaml" in checks_for(rep, severity="HIGH")


def test_ignore_list():
    from helmreview.checks import analyze
    from helmreview.helm import parse_manifests
    from helmreview.models import ChartReport

    rep = ChartReport(chart="x", ignored={"image-tag"})
    analyze(
        rep,
        parse_manifests(
            "kind: Pod\napiVersion: v1\nmetadata: {name: p}\nspec: {containers: [{name: c, image: nginx}]}"
        ),
        "default",
    )
    assert "image-tag" not in checks_for(rep)
    assert "resources" in checks_for(rep)
