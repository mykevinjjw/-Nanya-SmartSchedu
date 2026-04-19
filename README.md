# 🎓 南亞技術學院 - 自動排課管理系統 (Pro)

本專案是一個基於 BDD (Behavior-Driven Development) 理念開發的自動化排課解決方案，旨在協助教務人員高效、準確地管理全校課程、教師與教室資源。

---

## 👥 使用者角色 (User Personas)

*   **作為一個 系辦行政人員**：我想要 輕鬆維護教師與課程資料，以便 隨時應對突發的人事與科目變動。
*   **作為一個 教務處排課員**：我想要 系統自動根據複雜的校規進行排課，以便 避免人工排課造成的衝堂與違規。
*   **作為一個 授課教師**：我想要 清晰地檢視個人的專屬課表與總學分統計，以便 安排個人的研究與教學進度。

---

## 🌟 核心功能規格 (BDD Features)

### 1. 課程與資源維護 (Data Management)
**價值：** 確保排課的基礎資料準確且具備彈性。
*   **Scenario: 新增具備特定屬性的教師**
    *   **Given** 管理員進入「資料管理」介面。
    *   **When** 輸入老師姓名、選擇職稱（如：專業教師）並設定屬性（如：⭐ 系主任）。
    *   **Then** 系統應自動套用該職位的限制規則（如：系主任週二上午不排課）。

### 2. 智慧排課邏輯 (Automatic Scheduling)
**價值：** 嚴格遵守校規，實現自動化配置。
*   **Scenario: 驗證行政禁排時段**
    *   **When** 點擊「一鍵自動排課」。
    *   **Then** 週五全天、週四下午（第 5-8 節）必須保持完全清空。

### 3. 視覺化分析與教師視角 (Visual Interaction)
**價值：** 提供直覺的資源監控與行程追蹤。
*   **Scenario: 教師授課時數統計**
    *   **When** 展開右側「教師統計欄」。
    *   **Then** 系統應列出所有老師，並按其在當前課表中所佔的總學分（節數）進行排序。

### 4. 正式報表輸出 (PDF Export)
**價值：** 產出符合學術規範的正式文件。
*   **Scenario: 匯出 A4 單頁直式 PDF**
    *   **Given** 使用者已設定好學年度與學期。
    *   **When** 點擊「匯出 PDF」。
    *   **Then** 系統應產生一張縮放比例為 90%、內容水平置中、標題正式的 A4 直式課表檔案。

---

## 🛠️ 技術架構 (Technical Stack)

*   **後端**: Python (FastAPI), Google OR-Tools (Constraint Programming), SQLAlchemy.
*   **前端**: Vanilla JavaScript, CSS Grid, HTML5 (Datalist), window.print (Optimized for PDF).
*   **資料庫**: 
    *   開發環境：SQLite (檔案位於 `backend/course_schedule.db`).
    *   生產環境：支援 PostgreSQL (可透過 Docker 快速啟動).
*   **容器化**: **Docker & Docker Compose** (用於標準化開發環境與資料庫部署).

---

## 🚀 快速啟動 (Quick Start)

### 方案 A：本地 Python 環境 (推薦開發使用)
1.  **安裝套件**: `pip install -r backend/requirements.txt`
2.  **初始化資料**: `python backend/init_db.py`
3.  **啟動後端**: `python backend/main.py`
4.  **啟動前端**: `python -m http.server 9001 --directory frontend`

### 方案 B：Docker 容器化部署 (推薦生產使用)
1.  **啟動資料庫服務**:
    ```bash
    docker-compose -f backend/docker-compose.yml up -d
    ```
2.  **系統將自動連結 Docker 中的 PostgreSQL 資料庫**，提供更穩定的資料儲存。

---

## 🛡️ Git 開發規範
*   **測試隔離**: 所有的 `.db` 檔案、`features/` 資料夾及測試腳本均已加入 `.gitignore`，嚴禁上傳至 GitHub，以保護資料隱私與倉庫整潔。
