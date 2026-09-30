"""Tablas de referencia. Mantener actualizadas con cada versión de Kubernetes/OpenShift."""

import re

WORKLOADS = {"Deployment", "DeploymentConfig", "StatefulSet", "DaemonSet", "ReplicaSet", "Job", "CronJob", "Pod"}
SCALABLE = ("Deployment", "DeploymentConfig", "StatefulSet", "ReplicaSet")

# apiVersion -> versión de Kubernetes en la que se eliminó.
# Fuente: https://kubernetes.io/docs/reference/using-api/deprecation-guide/
DEPRECATED_APIS = {
    "extensions/v1beta1": "1.22",
    "apps/v1beta1": "1.16",
    "apps/v1beta2": "1.16",
    "networking.k8s.io/v1beta1": "1.22",
    "rbac.authorization.k8s.io/v1beta1": "1.22",
    "apiextensions.k8s.io/v1beta1": "1.22",
    "admissionregistration.k8s.io/v1beta1": "1.22",
    "scheduling.k8s.io/v1beta1": "1.22",
    "certificates.k8s.io/v1beta1": "1.22",
    "coordination.k8s.io/v1beta1": "1.22",
    "storage.k8s.io/v1beta1": "1.22 (CSIStorageCapacity: 1.27)",
    "policy/v1beta1": "1.25",
    "batch/v1beta1": "1.25",
    "autoscaling/v2beta1": "1.25",
    "autoscaling/v2beta2": "1.26",
    "discovery.k8s.io/v1beta1": "1.25",
    "events.k8s.io/v1beta1": "1.25",
    "node.k8s.io/v1beta1": "1.25",
    "flowcontrol.apiserver.k8s.io/v1beta1": "1.26",
    "flowcontrol.apiserver.k8s.io/v1beta2": "1.29",
    "flowcontrol.apiserver.k8s.io/v1beta3": "1.32",
}

SECRET_ENV = re.compile(r"(PASSWORD|PASSWD|\bPWD\b|SECRET|TOKEN|API_?KEY|PRIVATE_?KEY|CREDENTIALS?)", re.I)
DANGEROUS_CAPS = {"ALL", "SYS_ADMIN", "NET_ADMIN", "SYS_PTRACE", "SYS_MODULE", "DAC_READ_SEARCH", "BPF"}
PINNED_SEMVER = re.compile(r"^v?\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$")

# ---- OpenShift ----
# APIs que expone un cluster OpenShift; se pasan a `helm template` para que los condicionales
# .Capabilities.APIVersions.Has "route.openshift.io/v1" rendericen igual que en el cluster.
OCP_API_VERSIONS = [
    "route.openshift.io/v1",
    "route.openshift.io/v1/Route",
    "security.openshift.io/v1",
    "security.openshift.io/v1/SecurityContextConstraints",
    "apps.openshift.io/v1",
    "image.openshift.io/v1",
    "build.openshift.io/v1",
    "project.openshift.io/v1",
    "config.openshift.io/v1",
    "monitoring.coreos.com/v1",
    "monitoring.coreos.com/v1/ServiceMonitor",
]

# Versión OpenShift -> versión de Kubernetes. Agregar aquí las nuevas versiones de OCP.
OCP_KUBE_MAP = {
    "4.12": "1.25",
    "4.13": "1.26",
    "4.14": "1.27",
    "4.15": "1.28",
    "4.16": "1.29",
    "4.17": "1.30",
    "4.18": "1.31",
    "4.19": "1.32",
    "4.20": "1.33",
}

# Única capability que la SCC restricted-v2 permite agregar.
OCP_ALLOWED_CAPS = {"NET_BIND_SERVICE"}
