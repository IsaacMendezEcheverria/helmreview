import json
import shutil

import pytest

from conftest import FIXTURES
from helmreview import __version__
from helmreview.cli import main
from helmreview.helm import template_cmd
from helmreview.options import ReviewOptions

DEMO = str(FIXTURES / "charts" / "demo")
SAMPLE = str(FIXTURES / "charts" / "sample")
K8S_ISSUES = str(FIXTURES / "rendered" / "k8s_issues.yaml")

needs_helm = pytest.mark.skipif(shutil.which("helm") is None, reason="helm no está instalado")


def test_version(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--version"])
    assert e.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_rendered_mode_reports(tmp_path):
    md, js = tmp_path / "r.md", tmp_path / "r.json"
    rc = main([DEMO, "--rendered", K8S_ISSUES, "--report", str(md), "--json", str(js), "--no-color"])
    assert rc == 0
    assert "## demo" in md.read_text()
    data = json.loads(js.read_text())
    assert data["tool"] == "helmreview" and data["charts"][0]["name"] == "demo"


def test_fail_on_exit_code():
    assert main([DEMO, "--rendered", K8S_ISSUES, "--fail-on", "high", "--no-color"]) == 2


def test_ignore_flag(tmp_path):
    js = tmp_path / "r.json"
    main([DEMO, "--rendered", K8S_ISSUES, "--ignore", "image-tag,secret-en-env", "--json", str(js), "--no-color"])
    checks = {f["check"] for f in json.loads(js.read_text())["charts"][0]["findings"]}
    assert not {"image-tag", "secret-en-env"} & checks


def test_ocp_version_sets_platform_and_kube_version(tmp_path):
    md = tmp_path / "r.md"
    main([DEMO, "--rendered", K8S_ISSUES, "--ocp-version", "4.16", "--report", str(md), "--no-color"])
    text = md.read_text()
    assert "`openshift` (OCP 4.16)" in text and "`1.29`" in text


def test_unknown_ocp_version_errors():
    with pytest.raises(SystemExit):
        main([DEMO, "--rendered", K8S_ISSUES, "--ocp-version", "3.11"])


def test_template_cmd_openshift_adds_api_versions():
    cmd = template_cmd("c", "r", ReviewOptions(platform="openshift", kube_version="1.29", values=["v.yaml"]))
    assert "route.openshift.io/v1" in cmd and "--kube-version" in cmd and "v.yaml" in cmd
    assert "route.openshift.io/v1" not in template_cmd("c", "r", ReviewOptions())


@needs_helm
def test_helm_sample_chart_kubernetes(tmp_path):
    js = tmp_path / "r.json"
    rc = main([SAMPLE, "--json", str(js), "--fail-on", "medium", "--no-color"])
    chart = json.loads(js.read_text())["charts"][0]
    assert "Route" not in chart["resources_count"]
    assert rc == 0, chart["findings"]


@needs_helm
def test_helm_sample_chart_openshift_renders_route(tmp_path):
    js = tmp_path / "r.json"
    rc = main([SAMPLE, "--ocp-version", "4.16", "--json", str(js), "--fail-on", "medium", "--no-color"])
    chart = json.loads(js.read_text())["charts"][0]
    assert chart["resources_count"].get("Route") == 1
    assert rc == 0, chart["findings"]
