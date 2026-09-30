from conftest import analyze_file, analyze_text, checks_for


def test_ocp_issues_detected():
    rep = analyze_file("ocp_issues.yaml", "openshift")
    dc = "DeploymentConfig/legacy"
    assert {"ocp-uid", "ocp-scc"} <= checks_for(rep, dc, "HIGH")
    assert "ocp-caps" in checks_for(rep, dc, "HIGH")
    assert {"ocp-deploymentconfig", "ocp-puerto"} <= checks_for(rep, dc, "MEDIUM")
    assert "ocp-route-tls" in checks_for(rep, "Route/api")
    assert "ocp-scc-rbac" in checks_for(rep, "RoleBinding/legacy-anyuid")


def test_ocp_compliant_deployment_is_clean():
    rep = analyze_file("ocp_issues.yaml", "openshift")
    serious = [f for f in rep.findings if f.resource == "Deployment/api" and f.severity in ("HIGH", "MEDIUM")]
    assert serious == [], serious


def test_openshift_does_not_ask_for_runasuser():
    """En Kubernetes se pide garantizar no-root; en OpenShift la SCC lo hace y fijar UID es un error."""
    manifest = """
apiVersion: apps/v1
kind: Deployment
metadata: {name: x}
spec:
  replicas: 2
  template:
    spec:
      containers: [{name: c, image: a:1}]
"""
    k8s = [f.message for f in analyze_text(manifest).findings]
    ocp = [f.message for f in analyze_text(manifest, "openshift").findings]
    assert any("no-root" in m for m in k8s)
    assert not any("no-root" in m for m in ocp)


def test_scc_summary_lists_required_sccs():
    rep = analyze_text(
        """
apiVersion: apps/v1
kind: DaemonSet
metadata: {name: agent}
spec:
  template:
    spec:
      hostNetwork: true
      volumes: [{name: v, hostPath: {path: /var/log}}]
      containers: [{name: c, image: a:1, securityContext: {runAsUser: 0}}]
""",
        "openshift",
    )
    msg = next(f.message for f in rep.findings if f.check == "ocp-scc")
    for scc in ("anyuid", "hostmount-anyuid", "hostnetwork-v2"):
        assert scc in msg


def test_net_bind_service_is_allowed():
    rep = analyze_text(
        """
apiVersion: v1
kind: Pod
metadata: {name: p}
spec:
  containers:
  - name: c
    image: a:1
    ports: [{containerPort: 80}]
    securityContext: {capabilities: {add: [NET_BIND_SERVICE], drop: [ALL]}}
""",
        "openshift",
    )
    assert not {"ocp-caps", "ocp-puerto", "ocp-scc"} & checks_for(rep)


def test_scc_object_and_ingress_in_openshift():
    rep = analyze_text(
        """
apiVersion: security.openshift.io/v1
kind: SecurityContextConstraints
metadata: {name: custom}
allowPrivilegedContainer: true
runAsUser: {type: RunAsAny}
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: i
  annotations: {route.openshift.io/termination: edge}
spec: {rules: []}
""",
        "openshift",
    )
    scc = next(f for f in rep.findings if f.resource == "SecurityContextConstraints/custom")
    assert scc.severity == "HIGH" and "allowPrivilegedContainer" in scc.message
    ing = checks_for(rep, "Ingress/i")
    assert "ocp-ingress" in ing and "ingress-tls" not in ing
