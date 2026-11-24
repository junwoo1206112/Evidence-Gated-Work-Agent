from __future__ import annotations

from tests.conftest import SUFFICIENT_REQUEST, approve, create_run, run_id_of


def test_home_page_has_honest_notice_and_presets(client) -> None:
    response = client.get("/")
    assert response.status_code == 200
    text = response.text
    assert "실제 조달" in text
    assert "LLM" in text
    assert "검증: pytest 156" in text
    assert "/docs/verification" in text
    script = client.get("/static/app.js").text
    assert "근거가 부족하면" in script
    for preset in ["충분 근거", "부족 근거", "상충 근거", "실패 → 자동 재시도"]:
        assert preset in script


def test_score_threshold_is_visible_in_ui_source(client) -> None:
    source = client.get("/static/app.js").text
    css = client.get("/static/styles.css").text
    assert "SCORE_THRESHOLD = 0.42" in source
    assert "meter-threshold" in source
    assert ".meter-threshold" in css
    assert "left: 42%" in css


def test_home_page_has_no_secret_inputs(client) -> None:
    text = (client.get("/").text + client.get("/static/app.js").text).lower()
    assert 'type="password"' not in text
    assert "api_key" not in text
    assert 'name="email"' not in text


def test_home_page_labels_and_semantics(client) -> None:
    text = client.get("/").text
    script = client.get("/static/app.js").text
    assert 'lang="ko"' in text
    assert '"request-input"' in script
    assert '"demo-mode"' in script
    assert "role: \"alert\"" in script or 'role: "alert"' in script or 'role="alert"' in script


def test_run_page_contains_run_id(client) -> None:
    run_id = run_id_of(create_run(client))
    response = client.get(f"/runs/{run_id}")
    assert response.status_code == 200
    assert f'data-run-id="{run_id}"' in response.text
    assert "/static/app.js" in response.text


def test_missing_run_page_is_404_and_has_no_inline_script(client) -> None:
    response = client.get("/runs/run_missing")
    assert response.status_code == 404
    assert "찾을 수 없습니다" in response.text
    assert "<script>" not in response.text


def test_javascript_uses_text_content_not_inner_html(client) -> None:
    source = client.get("/static/app.js").text
    assert "textContent" in source
    assert "innerHTML" not in source
    assert "document.write" not in source
    assert "eval(" not in source


def test_xss_payload_is_rejected(client) -> None:
    response = create_run(client, "<script>alert(1)</script> 계약보증금 확인")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "E_SENSITIVE_INPUT"


def test_benign_markup_is_not_echoed_into_server_html(client) -> None:
    payload = "<b>안전한가?</b> 계약보증금 확인"
    response = create_run(client, payload)
    assert response.status_code == 201
    run_id = response.json()["run"]["run_id"]
    page = client.get(f"/runs/{run_id}")
    assert payload not in page.text
    assert "&lt;b&gt;" not in page.text


def test_ui_capabilities_match_api_state(client) -> None:
    pending = create_run(client).json()
    assert pending["capabilities"]["can_approve"] is True
    assert pending["capabilities"]["can_execute"] is False
    run_id = pending["run"]["run_id"]
    approve(client, run_id)
    approved = client.get(f"/api/runs/{run_id}").json()
    assert approved["capabilities"]["can_execute"] is True
    page = client.get(f"/runs/{run_id}")
    assert page.status_code == 200
