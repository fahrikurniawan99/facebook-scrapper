import os
import uuid
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field
from scraper import scrape_group, DEFAULT_GROUP_URL, STATE_FILE

app = FastAPI(
    title="Facebook Group Scraper API",
    description="REST API untuk crawling postingan dan komentar grup Facebook secara otomatis di latar belakang (Headless).",
    version="1.0.0"
)

# Penyimpanan in-memory untuk asynchronous jobs
jobs_db = {}

# Pydantic Schemas
class CommentItem(BaseModel):
    pengomentar: str = Field(..., example="Alin R Mktr Zaka")
    waktu: str = Field("", example="1hari")
    teks: str = Field(..., example="Kak caranya??")

class PostItem(BaseModel):
    id: str = Field(..., example="3caa21720f")
    penulis: str = Field(..., example="Indri Putri Natasya")
    waktu_post: str = Field(..., example="5 hari yang lalu")
    teks_postingan: str = Field(..., example="Ready DAPIN...")
    jumlah_suka: int = Field(0, example=31)
    total_komentar_fb: int = Field(0, example=70)
    komentar_terkumpul: int = Field(0, example=2)
    semua_komentar: str = Field("", example="[1] Alin R Mktr Zaka (1hari): Kak caranya??")
    url_post: str = Field("", example="https://facebook.com/groups/.../posts/...")
    url_profil: str = Field("", example="https://facebook.com/groups/.../user/...")
    url_gambar: str = Field("", example="")
    daftar_komentar: List[CommentItem] = Field(default_factory=list)
    scraped_at: str = Field(..., example="2026-09-28 08:30:00")

class ScrapeResponse(BaseModel):
    status: str = "success"
    target_url: str
    total_posts: int
    scraped_at: str
    data: List[PostItem]

class ScrapeRequest(BaseModel):
    url: Optional[str] = Field(DEFAULT_GROUP_URL, description="URL Facebook Group")
    scrolls: int = Field(10, ge=1, le=100, description="Jumlah scroll feed")
    delay: float = Field(2.5, ge=1.0, le=10.0, description="Jeda detik antar scroll")
    save_files: bool = Field(False, description="Simpan juga ke CSV/Excel di server")

class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    created_at: str
    completed_at: Optional[str] = None
    total_posts: Optional[int] = 0
    data: Optional[List[PostItem]] = None
    error: Optional[str] = None

@app.get("/", tags=["Health"])
def root():
    session_ready = os.path.exists(STATE_FILE)
    return {
        "app": "Facebook Group Scraper API",
        "status": "online",
        "session_ready": session_ready,
        "docs_url": "/docs",
        "message": "Sesi siap digunakan" if session_ready else "Peringatan: state.json belum ada. Jalankan login.py atau import_cookie.py terlebih dahulu."
    }

@app.get("/api/health", tags=["Health"])
def health():
    return {
        "status": "healthy",
        "session_exists": os.path.exists(STATE_FILE),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

@app.get("/api/scrape", response_model=ScrapeResponse, tags=["Scraping (Synchronous)"])
def scrape_get(
    url: str = Query(DEFAULT_GROUP_URL, description="URL Grup Facebook"),
    scrolls: int = Query(5, ge=1, le=50, description="Jumlah perulangan auto-scroll feed"),
    delay: float = Query(2.5, ge=1.0, le=10.0, description="Jeda waktu antar scroll (detik)"),
    save_files: bool = Query(False, description="Simpan juga file CSV/Excel ke server")
):
    """
    Eksekusi scraping langsung (Sinkron).
    Browser Chromium berjalan 100% headless di memori server dan langsung mengembalikan JSON.
    Cocok untuk 5-15 scroll.
    """
    if not os.path.exists(STATE_FILE):
        raise HTTPException(
            status_code=400,
            detail="File 'state.json' belum ditemukan. Silakan login atau impor cookie terlebih dahulu di server."
        )

    try:
        raw_results = scrape_group(
            url=url,
            max_scrolls=scrolls,
            base_delay=delay,
            headless=True,
            save_files=save_files
        )

        formatted_posts = []
        for r in raw_results:
            comments = [
                CommentItem(
                    pengomentar=c.get("pengomentar", ""),
                    waktu=c.get("waktu", ""),
                    teks=c.get("teks", "")
                )
                for c in r.get("daftar_komentar", [])
            ]

            formatted_posts.append(PostItem(
                id=r.get("id", ""),
                penulis=r.get("penulis", ""),
                waktu_post=r.get("waktu_post", ""),
                teks_postingan=r.get("teks_postingan", ""),
                jumlah_suka=int(r.get("jumlah_suka") or 0),
                total_komentar_fb=int(r.get("total_komentar_fb") or 0),
                komentar_terkumpul=r.get("komentar_terkumpul", 0),
                semua_komentar=r.get("semua_komentar", ""),
                url_post=r.get("url_post", ""),
                url_profil=r.get("url_profil", ""),
                url_gambar=r.get("url_gambar", ""),
                daftar_komentar=comments,
                scraped_at=r.get("scraped_at", "")
            ))

        return ScrapeResponse(
            status="success",
            target_url=url,
            total_posts=len(formatted_posts),
            scraped_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            data=formatted_posts
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal melakukan scraping: {str(e)}")

@app.post("/api/scrape", response_model=ScrapeResponse, tags=["Scraping (Synchronous)"])
def scrape_post(req: ScrapeRequest):
    """Versi POST untuk request scraping langsung via JSON body."""
    return scrape_get(
        url=req.url or DEFAULT_GROUP_URL,
        scrolls=req.scrolls,
        delay=req.delay,
        save_files=req.save_files
    )

def run_background_scrape(job_id: str, url: str, scrolls: int, delay: float, save_files: bool):
    try:
        raw_results = scrape_group(
            url=url,
            max_scrolls=scrolls,
            base_delay=delay,
            headless=True,
            save_files=save_files
        )
        formatted_posts = []
        for r in raw_results:
            comments = [
                CommentItem(
                    pengomentar=c.get("pengomentar", ""),
                    waktu=c.get("waktu", ""),
                    teks=c.get("teks", "")
                )
                for c in r.get("daftar_komentar", [])
            ]
            formatted_posts.append(PostItem(
                id=r.get("id", ""),
                penulis=r.get("penulis", ""),
                waktu_post=r.get("waktu_post", ""),
                teks_postingan=r.get("teks_postingan", ""),
                jumlah_suka=int(r.get("jumlah_suka") or 0),
                total_komentar_fb=int(r.get("total_komentar_fb") or 0),
                komentar_terkumpul=r.get("komentar_terkumpul", 0),
                semua_komentar=r.get("semua_komentar", ""),
                url_post=r.get("url_post", ""),
                url_profil=r.get("url_profil", ""),
                url_gambar=r.get("url_gambar", ""),
                daftar_komentar=comments,
                scraped_at=r.get("scraped_at", "")
            ))
        jobs_db[job_id]["status"] = "completed"
        jobs_db[job_id]["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        jobs_db[job_id]["total_posts"] = len(formatted_posts)
        jobs_db[job_id]["data"] = formatted_posts
    except Exception as e:
        jobs_db[job_id]["status"] = "failed"
        jobs_db[job_id]["error"] = str(e)

@app.post("/api/scrape-async", tags=["Scraping (Background Job)"])
def scrape_async(req: ScrapeRequest, background_tasks: BackgroundTasks):
    """
    Menjalankan proses scraping di background.
    Mengembalikan job_id langsung tanpa menunggu proses scraping selesai.
    Cocok untuk scraping dengan jumlah scroll banyak (> 20 scroll).
    """
    if not os.path.exists(STATE_FILE):
        raise HTTPException(
            status_code=400,
            detail="File 'state.json' belum ditemukan. Silakan login atau impor cookie terlebih dahulu."
        )

    job_id = str(uuid.uuid4())[:8]
    jobs_db[job_id] = {
        "job_id": job_id,
        "status": "processing",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "completed_at": None,
        "total_posts": 0,
        "data": None,
        "error": None
    }

    background_tasks.add_task(
        run_background_scrape,
        job_id=job_id,
        url=req.url or DEFAULT_GROUP_URL,
        scrolls=req.scrolls,
        delay=req.delay,
        save_files=req.save_files
    )

    return {
        "job_id": job_id,
        "status": "processing",
        "check_status_url": f"/api/jobs/{job_id}",
        "message": "Scraping sedang berjalan di latar belakang server."
    }

@app.get("/api/jobs/{job_id}", response_model=JobStatusResponse, tags=["Scraping (Background Job)"])
def get_job_status(job_id: str):
    """Cek status dan ambil hasil scraping dari background job."""
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="Job ID tidak ditemukan.")
    return jobs_db[job_id]

if __name__ == "__main__":
    import uvicorn
    print("=" * 65)
    print(" Memulai Server Facebook Scraper API...")
    print(" Buka dokumentasi Swagger UI di: http://localhost:8000/docs")
    print("=" * 65)
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
