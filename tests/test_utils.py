import pytest

from helmreview.k8s import image_ref, pod_template, selector_matches
from helmreview.quantities import fmt_cpu, fmt_mem, parse_cpu, parse_mem


@pytest.mark.parametrize(
    "value,expected",
    [("250m", 250), ("1", 1000), (2, 2000), ("0.5", 500), ("abc", None), (None, None)],
)
def test_parse_cpu(value, expected):
    assert parse_cpu(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [("128Mi", 128 * 2**20), ("1Gi", 2**30), ("1G", 1e9), ("500k", 5e5), ("1024", 1024), ("x1Gi", None)],
)
def test_parse_mem(value, expected):
    assert parse_mem(value) == expected


def test_fmt():
    assert fmt_cpu(250) == "250m"
    assert fmt_cpu(1500) == "1.5"
    assert fmt_cpu(0) == "-"
    assert fmt_mem(512 * 2**20) == "512Mi"
    assert fmt_mem(1.5 * 2**30) == "1.5Gi"


@pytest.mark.parametrize(
    "image,expected",
    [
        ("nginx", ("none", "")),
        ("nginx:latest", ("tag", "latest")),
        ("registry.local:5000/app", ("none", "")),  # el puerto del registry no es un tag
        ("registry.local:5000/app:1.2", ("tag", "1.2")),
        ("app@sha256:abc", ("digest", "sha256:abc")),
    ],
)
def test_image_ref(image, expected):
    assert image_ref(image) == expected


def test_selector_matches():
    labels = {"app": "web", "tier": "front"}
    assert selector_matches({}, labels)  # selector vacío = todos
    assert not selector_matches(None, labels)
    assert selector_matches({"matchLabels": {"app": "web"}}, labels)
    assert not selector_matches({"matchLabels": {"app": "db"}}, labels)
    assert selector_matches({"matchExpressions": [{"key": "tier", "operator": "In", "values": ["front"]}]}, labels)
    assert not selector_matches({"matchExpressions": [{"key": "x", "operator": "Exists"}]}, labels)


def test_pod_template_cronjob():
    obj = {
        "kind": "CronJob",
        "spec": {
            "jobTemplate": {"spec": {"template": {"metadata": {"labels": {"a": "b"}}, "spec": {"containers": []}}}}
        },
    }
    meta, spec = pod_template(obj)
    assert meta["labels"] == {"a": "b"}
    assert spec == {"containers": []}
