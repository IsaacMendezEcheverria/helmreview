from conftest import FIXTURES
from helmreview.checks import check_chart_meta
from helmreview.models import ChartReport


def _run(meta, chart="nonexistent"):
    rep = ChartReport(chart=chart)
    check_chart_meta(rep, chart, meta)
    return rep


def test_metadata_is_read():
    rep = _run({"apiVersion": "v2", "name": "x", "version": "1.2.3", "appVersion": "9", "kubeVersion": ">=1.25"})
    assert (rep.name, rep.version, rep.app_version) == ("x", "1.2.3", "9")
    assert rep.findings == []


def test_helm2_chart_and_missing_kubeversion():
    checks = {f.check for f in _run({"apiVersion": "v1", "name": "x", "version": "1"}).findings}
    assert {"chart-apiversion", "chart-kubeversion", "chart-appversion"} <= checks


def test_unpinned_and_http_dependency():
    rep = _run(
        {
            "apiVersion": "v2",
            "name": "x",
            "version": "1",
            "appVersion": "1",
            "kubeVersion": ">=1",
            "dependencies": [
                {"name": "redis", "version": "~17.0", "repository": "http://repo"},
                {"name": "pg", "version": "12.1.0", "repository": "https://repo"},
            ],
        }
    )
    msgs = [f.message for f in rep.findings if f.check == "chart-dependency"]
    assert any("redis" in m and "no fijada" in m for m in msgs)
    assert any("HTTP" in m for m in msgs)
    assert not any("'pg'" in m for m in msgs)


def test_chart_dir_files():
    chart = str(FIXTURES / "charts" / "demo")  # sin values.schema.json ni Chart.lock
    rep = _run(
        {"apiVersion": "v2", "name": "demo", "version": "1", "dependencies": [{"name": "a", "version": "1.0.0"}]}, chart
    )
    checks = {f.check for f in rep.findings}
    assert {"chart-schema", "chart-lock"} <= checks


def test_sample_chart_is_clean():
    chart = FIXTURES / "charts" / "sample"
    import yaml

    rep = _run(yaml.safe_load((chart / "Chart.yaml").read_text()), str(chart))
    assert rep.findings == []
