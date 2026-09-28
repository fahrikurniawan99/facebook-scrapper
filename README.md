# Facebook Group Scraper & REST API (Python + Playwright + FastAPI)

Project otomatisasi untuk melakukan crawling postingan grup Facebook dengan fitur **Auto-Scroll**, menyatukan postingan dan komentarnya ke dalam **1 baris lengkap**, serta menyediakan **REST API siap pakai (Headless)**.

---

## 📁 Struktur Direktori

```text
D:\fb-scrap\
├── requirements.txt   # Dependensi (playwright, pandas, openpyxl, fastapi, uvicorn)
├── login.py           # Skrip login interaktif (cukup sekali di awal)
├── import_cookie.py   # Alternatif import cookie dari Chrome biasa
├── scraper.py         # Mesin scraper CLI & modul engine
├── api.py             # Server REST API (FastAPI)
├── .gitignore         # Mengabaikan file sensitif
└── output/            # Folder hasil export CSV, Excel, JSON
```

---

## 🌐 Menjalankan Sebagai REST API (Headless Server)

Browser Chromium akan berjalan 100% di memori latar belakang tanpa memunculkan jendela di layar.

### 1. Jalankan Server API
```powershell
cd D:\fb-scrap
python -m uvicorn api:app --reload --port 8000
```

### 2. Akses Dokumentasi Swagger UI
Buka di browser:
👉 **http://localhost:8000/docs**

### 3. Endpoint Tersedia:
* `GET /`: Health check & cek ketersediaan sesi `state.json`.
* `GET /api/scrape?scrolls=10`: Scraping sinkron langsung mengembalikan data JSON.
* `POST /api/scrape`: Versi POST dengan JSON payload.
* `POST /api/scrape-async`: Mode background job untuk tugas panjang (mengembalikan `job_id`).
* `GET /api/jobs/{job_id}`: Cek status dan ambil data dari background job.

---

## 💻 Menjalankan Sebagai CLI (Langsung Simpan File)

Jika ingin dijalankan langsung di terminal dan mengekspor ke file Excel/CSV:

```powershell
python scraper.py --scrolls 20
```

Hasil tersimpan otomatis di folder `output/` dalam format `.csv`, `.xlsx`, dan `.json`.
