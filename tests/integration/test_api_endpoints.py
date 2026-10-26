"""
整合測試：API 端點
使用 FastAPI TestClient 測試整合後之 SheetMusicOMR v3.00 + ScoreOCR Toolkit API 端點
"""

import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image


@pytest.fixture
def client():
    """建立測試客戶端"""
    from app import app
    with TestClient(app, base_url="http://127.0.0.1") as tc:
        yield tc


@pytest.fixture
def sample_png():
    """建立測試用 PNG 圖片"""
    img = Image.new("RGB", (200, 200), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()


@pytest.fixture
def sample_jianpu_txt():
    """測試用簡譜文字"""
    return b"1 2 3 4 5 6 7 1"


@pytest.fixture
def sample_json():
    """測試用 JSON 符號"""
    data = {
        "symbols": [
            {"id": "1", "type": "note", "pitch": "C4", "duration": "quarter", "x": 100, "y": 100, "width": 20, "height": 18, "confidence": 1.0},
            {"id": "2", "type": "note", "pitch": "D4", "duration": "quarter", "x": 150, "y": 100, "width": 20, "height": 18, "confidence": 1.0},
        ]
    }
    return json.dumps(data).encode("utf-8")


class TestHealthEndpoint:
    """健康檢查端點"""

    def test_health(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data

    def test_api_health_v3(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "engine" in data
        assert "version" in data


class TestSampleEndpoint:
    """示範樂譜端點"""

    def test_sample(self, client):
        response = client.get("/api/sample")
        assert response.status_code == 200
        data = response.json()
        assert data["filename"] == "tabi.png"
        assert "image_url" in data
        assert data["symbol_count"] > 0
        assert "symbols" in data
        assert "jianpu_text" in data


class TestUploadEndpoint:
    """上傳端點"""

    def test_upload_png(self, client, sample_png):
        response = client.post("/upload", files={"file": ("test.png", sample_png, "image/png")})
        assert response.status_code == 200
        data = response.json()
        assert data["filename"] == "test.png"
        assert "uploaded" in data
        assert "processed" in data
        assert data["next_step"] == "OMR recognition"

    def test_upload_jianpu_txt(self, client, sample_jianpu_txt):
        response = client.post("/upload", files={"file": ("test.txt", sample_jianpu_txt, "text/plain")})
        assert response.status_code == 200

    def test_upload_invalid_extension(self, client):
        response = client.post("/upload", files={"file": ("test.xyz", b"content", "application/octet-stream")})
        assert response.status_code == 400
        data = response.json()
        assert "不支援的檔案格式" in data["detail"]


class TestRecognizeEndpoint:
    """辨識端點 - 核心功能"""

    def test_recognize_jianpu_txt(self, client, sample_jianpu_txt):
        response = client.post("/recognize", files={"file": ("test.txt", sample_jianpu_txt, "text/plain")})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["format_type"] == "txt"
        assert data["symbol_count"] == 8
        assert len(data["symbols"]) == 8
        assert data["musicxml"] is not None
        assert data["jianpu_file"] is not None
        assert "1=C" in data["jianpu_text"]

    def test_recognize_json(self, client, sample_json):
        response = client.post("/recognize", files={"file": ("test.json", sample_json, "application/json")})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["format_type"] == "json"
        assert data["symbol_count"] == 2

    def test_recognize_invalid_format(self, client):
        response = client.post("/recognize", files={"file": ("test.xyz", b"content", "application/octet-stream")})
        assert response.status_code == 400

    def test_recognize_file_too_large(self, client):
        """測試檔案過大 (50MB 限制)"""
        large_content = b"x" * (51 * 1024 * 1024)  # 51 MB
        response = client.post("/recognize", files={"file": ("large.txt", large_content, "text/plain")})
        assert response.status_code == 413
        data = response.json()
        assert "檔案過大" in data["detail"]


class TestExportEndpoints:
    """匯出端點"""

    def create_test_symbols(self):
        """建立測試用符號列表"""
        return [
            {"id": "sym-1", "type": "note", "pitch": "C4", "duration": "quarter", "x": 100, "y": 100, "width": 20, "height": 18, "confidence": 1.0},
            {"id": "sym-2", "type": "note", "pitch": "D4", "duration": "quarter", "x": 150, "y": 100, "width": 20, "height": 18, "confidence": 1.0},
            {"id": "sym-3", "type": "rest", "pitch": None, "duration": "quarter", "x": 200, "y": 100, "width": 20, "height": 18, "confidence": 1.0},
        ]

    def test_export_jianpu(self, client):
        symbols = self.create_test_symbols()
        response = client.post(
            "/api/export-jianpu",
            json={"symbols": symbols, "key": "G", "meter": "4/4", "title": "Test Export"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "download_url" in data
        assert "jianpu_text" in data
        assert "1=G" in data["jianpu_text"]
        assert "4" in data["jianpu_text"]  # C4 in key G = 4
        assert "5" in data["jianpu_text"]  # D4 in key G = 5
        assert "0" in data["jianpu_text"]  # rest

    def test_export_jianpu_missing_symbols(self, client):
        response = client.post("/api/export-jianpu", json={"symbols": []})
        assert response.status_code == 422  # Pydantic validation error

    def test_export_jianpu_invalid_key(self, client):
        symbols = self.create_test_symbols()
        response = client.post(
            "/api/export-jianpu",
            json={"symbols": symbols, "key": "H", "meter": "4/4"}  # H 不是有效調號
        )
        assert response.status_code == 422

    def test_export_jianpu_invalid_meter(self, client):
        symbols = self.create_test_symbols()
        response = client.post(
            "/api/export-jianpu",
            json={"symbols": symbols, "key": "C", "meter": "5/4"}  # 不支援的拍號
        )
        assert response.status_code == 422

    def test_convert_to_jianpu(self, client):
        symbols = self.create_test_symbols()
        response = client.post(
            "/api/convert-to-jianpu",
            json={"symbols": symbols, "key": "F", "meter": "3/4"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "tag_map" in data
        assert "jianpu_text" in data
        assert "sym-1" in data["tag_map"]
        assert "sym-2" in data["tag_map"]
        assert "sym-3" in data["tag_map"]

    def test_export_musicxml(self, client):
        symbols = self.create_test_symbols()
        response = client.post(
            "/api/export-musicxml",
            json={"symbols": symbols}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "download_url" in data

        # 驗證下載的 XML 內容
        download_url = data["download_url"]
        response2 = client.get(download_url)
        assert response2.status_code == 200
        xml_content = response2.text
        assert "<score-partwise" in xml_content
        assert "<step>C</step>" in xml_content
        assert "<step>D</step>" in xml_content
        assert "<rest/>" in xml_content

    def test_export_musicxml_double_accidentals(self, client):
        """測試雙升/雙降號正確輸出"""
        symbols = [
            {"id": "1", "type": "note", "pitch": "F##5", "duration": "quarter", "x": 100, "y": 100, "width": 20, "height": 18, "confidence": 1.0},
            {"id": "2", "type": "note", "pitch": "Dbb2", "duration": "quarter", "x": 150, "y": 100, "width": 20, "height": 18, "confidence": 1.0},
        ]
        response = client.post("/api/export-musicxml", json={"symbols": symbols})
        assert response.status_code == 200
        download_url = response.json()["download_url"]
        response2 = client.get(download_url)
        xml_content = response2.text
        assert "<alter>2</alter>" in xml_content  # F## = alter 2
        assert "<alter>-2</alter>" in xml_content  # Dbb = alter -2
        assert "<octave>5</octave>" in xml_content
        assert "<octave>2</octave>" in xml_content

    def test_export_musicxml_empty_symbols(self, client):
        response = client.post("/api/export-musicxml", json={"symbols": []})
        assert response.status_code == 422


class TestDownloadEndpoint:
    """下載端點"""

    def test_download_existing_file(self, client):
        # 先產生一個檔案
        symbols = [{"id": "1", "type": "note", "pitch": "C4", "duration": "quarter", "x": 100, "y": 100, "width": 20, "height": 18, "confidence": 1.0}]
        response = client.post("/api/export-musicxml", json={"symbols": symbols})
        download_url = response.json()["download_url"]
        filename = download_url.split("/")[-1]

        response2 = client.get(f"/download/{filename}")
        assert response2.status_code == 200
        assert "musicxml" in response2.headers.get("content-type", "")

    def test_download_nonexistent_file(self, client):
        response = client.get("/download/nonexistent.musicxml")
        assert response.status_code == 404

    def test_download_path_traversal_blocked(self, client):
        """路徑遍歷攻擊應被阻擋"""
        response = client.get("/download/../../etc/passwd")
        assert response.status_code == 404


class TestFaviconEndpoint:
    """Favicon 端點"""

    def test_favicon(self, client):
        response = client.get("/favicon.ico")
        assert response.status_code in (200, 204)


class TestUIEndpoint:
    """前端頁面與專業編輯器路由"""

    def test_root_workbench_ui(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert "SheetMusicOMR" in response.text
        assert "/canvas-editor" not in response.text

    def test_canvas_editor_removed(self, client):
        """驗證畫布視覺校對功能已移除，不再提供獨立畫布校對器"""
        response = client.get("/canvas-editor")
        assert "畫布視覺校對" not in response.text
        assert "視覺化樂譜校對畫布" not in response.text

        studio_resp = client.get("/editor/studio/default")
        assert studio_resp.status_code == 200
        assert "畫布校對" not in studio_resp.text

    def test_default_score_studio_mode_enabled(self, client):
        """驗證預設直接開啟「專業編輯」(Score Studio) 模式"""
        flags_resp = client.get("/api/flags/score-studio")
        assert flags_resp.status_code == 200
        flags = flags_resp.json()
        assert flags["enabled"] is True
        assert flags["default"] is True

        redir_resp = client.get("/editor/doc_test123", follow_redirects=False)
        assert redir_resp.status_code == 302
        assert redir_resp.headers["location"] == "/editor/studio/doc_test123"

    def test_import_from_canvas_to_sqlite_and_studio(self, client):
        """驗證從畫布一鍵將結果存入主工作台 SQLite 專案列表並回傳 Score Studio 連結"""
        symbols = [
            {"id": "c1", "type": "chord", "pitch": "C", "x": 100, "y": 80, "width": 24, "height": 16},
            {"id": "n1", "type": "note", "pitch": "C4", "duration": "quarter", "x": 100, "y": 100, "width": 18, "height": 16},
            {"id": "n2", "type": "note", "pitch": "D4", "duration": "eighth", "x": 140, "y": 100, "width": 18, "height": 16},
            {"id": "n3", "type": "note", "pitch": "E4", "duration": "eighth", "x": 170, "y": 100, "width": 18, "height": 16},
            {"id": "n4", "type": "note", "pitch": "G4", "duration": "half", "x": 210, "y": 100, "width": 18, "height": 16},
            {"id": "c2", "type": "chord", "pitch": "G7", "x": 300, "y": 80, "width": 24, "height": 16},
            {"id": "n5", "type": "note", "pitch": "A4", "duration": "16th", "x": 300, "y": 100, "width": 18, "height": 16},
            {"id": "n6", "type": "rest", "pitch": None, "duration": "quarter", "x": 340, "y": 100, "width": 18, "height": 16},
        ]
        resp = client.post(
            "/api/import-from-canvas",
            json={
                "project_name": "畫布匯入測試曲",
                "symbols": symbols,
                "key": "C",
                "meter": "4/4",
                "tempo": 88,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["ok"] is True
        project_id = data["projectId"]
        assert project_id.startswith("doc_")
        assert data["measureCount"] == 2
        assert data["studioUrl"] == f"/?project={project_id}"
        assert data["standaloneStudioUrl"] == f"/editor/studio/{project_id}"

        # 確認已寫入 SQLite 專案列表
        list_resp = client.get("/api/projects")
        assert list_resp.status_code == 200
        projects = list_resp.json()
        assert any(p.get("id") == project_id and p.get("title") == "畫布匯入測試曲" for p in projects)

        # 確認可從主工作台專案 API 與 ScoreStudio API 讀取完整小節內容
        doc_resp = client.get(f"/api/projects/{project_id}")
        assert doc_resp.status_code == 200
        doc = doc_resp.json()
        assert doc["title"] == "畫布匯入測試曲"
        assert len(doc["measures"]) == 2
        assert doc["measures"][0]["noteText"] == "1 2_ 3_ 5 -"
        assert doc["measures"][0]["chordText"] == "C"
        assert doc["measures"][1]["noteText"] == "6__ 0"
        assert doc["measures"][1]["chordText"] == "G7"
