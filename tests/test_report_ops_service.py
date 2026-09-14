import io
import json

from tools.report_ops_service import build_app, render_dashboard_html


def _call_app(app, method="GET", path="/", body=b"", content_type="application/x-www-form-urlencoded", accept="text/html"):
    captured = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = headers

    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "CONTENT_TYPE": content_type,
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.input": io.BytesIO(body),
        "HTTP_ACCEPT": accept,
    }
    response = b"".join(app(environ, start_response)).decode("utf-8")
    return captured["status"], dict(captured["headers"]), response


def test_render_dashboard_html_lists_clients():
    html = render_dashboard_html([{"client_key": "one-funded", "client_name": "One Funded"}])

    assert "One Funded" in html
    assert "Launch run" in html


def test_build_app_post_runs_returns_json():
    class Launcher:
        def launch(self, payload):
            assert payload["RUN_MODE"] == "one"
            assert payload["CLIENT_KEY"] == "one-funded"
            return {"name": "operations/123"}

    app = build_app(lambda: [{"client_key": "one-funded", "client_name": "One Funded"}], Launcher())
    body = json.dumps(
        {
            "run_mode": "one",
            "client_key": "one-funded",
            "month": "March",
            "year": "2026",
            "insights_provider": "deterministic",
        }
    ).encode("utf-8")

    status, headers, response = _call_app(
        app,
        method="POST",
        path="/runs",
        body=body,
        content_type="application/json",
        accept="application/json",
    )

    payload = json.loads(response)
    assert status == "202 Accepted"
    assert headers["Content-Type"] == "application/json"
    assert payload["status"] == "queued"
    assert payload["operation"] == "operations/123"


def test_build_app_post_runs_passes_ops_flags():
    class Launcher:
        def launch(self, payload):
            assert payload["RUN_MODE"] == "missing"
            assert payload["ALLOW_FIRST_MONTH_BASELINE"] == "true"
            assert payload["INCLUDE_INACTIVE"] == "true"
            return {"name": "operations/456"}

    app = build_app(lambda: [], Launcher())
    body = json.dumps(
        {
            "run_mode": "missing",
            "month": "May",
            "year": "2026",
            "insights_provider": "deterministic",
            "allow_first_month_baseline": "true",
            "include_inactive": "true",
        }
    ).encode("utf-8")

    status, _headers, response = _call_app(
        app,
        method="POST",
        path="/runs",
        body=body,
        content_type="application/json",
        accept="application/json",
    )

    assert status == "202 Accepted"
    assert json.loads(response)["operation"] == "operations/456"


def test_build_app_client_creation_preflight_and_activation_routes():
    class Ops:
        def list_clients(self, *_args):
            return [{"client_key": "one-funded", "client_name": "One Funded", "active": True}]

        def create_client(self, **kwargs):
            assert kwargs["client_name"] == "Lux Algo"
            return {"client_key": "lux-algo", "client_name": "Lux Algo"}

        def set_client_active(self, client_key, active):
            return {"client_key": client_key, "active": active}

        def preflight_report(self, **kwargs):
            assert kwargs["client_key"] == "lux-algo"
            assert kwargs["allow_first_month_baseline"] is True
            return {"status": "ok", "client_key": "lux-algo"}

    class Launcher:
        def launch(self, payload):
            return {"name": "operations/123"}

    app = build_app(lambda: [], Launcher(), ops=Ops())

    status, _headers, response = _call_app(
        app,
        method="POST",
        path="/clients",
        body=json.dumps({"client_name": "Lux Algo"}).encode("utf-8"),
        content_type="application/json",
        accept="application/json",
    )
    assert status == "201 Created"
    assert json.loads(response)["client"]["client_key"] == "lux-algo"

    status, _headers, response = _call_app(
        app,
        method="POST",
        path="/clients/lux-algo/activate",
        body=json.dumps({"active": "false"}).encode("utf-8"),
        content_type="application/json",
        accept="application/json",
    )
    assert status == "200 OK"
    assert json.loads(response)["client"]["active"] is False

    status, _headers, response = _call_app(
        app,
        method="POST",
        path="/reports/preflight",
        body=json.dumps(
            {
                "client_key": "lux-algo",
                "month": "May",
                "year": "2026",
                "allow_first_month_baseline": "true",
            }
        ).encode("utf-8"),
        content_type="application/json",
        accept="application/json",
    )
    assert status == "200 OK"
    assert json.loads(response)["status"] == "ok"
