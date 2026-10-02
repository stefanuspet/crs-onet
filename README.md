# crs-onet — Jelajah Karier

Sistem rekomendasi karier untuk siswa SMA berbasis data O*NET 31.0 (capstone project).
Siswa menjawab kuesioner minat adaptif (setiap jawaban menentukan pertanyaan berikutnya), lalu
mendapat daftar pekerjaan yang mungkin cocok beserta alasannya, jenjang pendidikan, kompetensi
yang perlu dikembangkan, dan karier serupa.

Catatan rancangan, hasil uji, dan keterbatasan ada di [`CRS_Context.md`](CRS_Context.md).

## Menjalankan di komputer sendiri

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/streamlit run streamlit_app.py
```

Aplikasi terbuka di `http://localhost:8501`. Tanpa pengaturan apa pun, jawaban disimpan di berkas
`data/crs.sqlite3` (tidak ikut ke repo).

`requirements.txt` hanya berisi kebutuhan aplikasi Streamlit; `requirements-dev.txt` menambah kebutuhan tes,
tampilan FastAPI, dan skrip eksperimen.

Tes: `.venv/bin/python -m unittest discover tests`

## Memasang di Streamlit Community Cloud

Berkas di server Streamlit Cloud bisa hilang saat aplikasi dinyalakan ulang, jadi jawaban siswa
**harus** disimpan di Postgres daring.

1. Buat basis data Postgres gratis (misalnya di Supabase atau Neon) dan salin alamat koneksinya
   (`postgresql://...`). Tabel dibuat otomatis saat aplikasi pertama kali jalan.
2. Di [share.streamlit.io](https://share.streamlit.io): **Create app** → pilih repo ini, cabang `main`,
   berkas utama `streamlit_app.py`.
3. Di **Advanced settings → Secrets**, isi (contoh ada di `.streamlit/secrets.toml.example`):

   ```toml
   DATABASE_URL = "postgresql://USER:PASSWORD@HOST:5432/DBNAME"
   ADMIN_TOKEN = "kata-sandi-panjang-untuk-ekspor"
   ```

4. Setelah aplikasi jalan, buka `https://<alamat-aplikasi>/?admin=1`, masukkan kata sandi, dan pastikan
   tertulis **Penyimpanan: postgres**. Kalau tertulis `sqlite`, `DATABASE_URL` belum terbaca dan data
   bisa hilang.

Kata sandi dan alamat basis data jangan pernah di-commit; `.streamlit/secrets.toml` sudah ada di `.gitignore`.

Aplikasi di Streamlit Cloud tertidur setelah 12 jam tanpa pengunjung. Buka dulu beberapa menit sebelum
sesi uji coba dimulai.

## Mengambil data uji coba

Buka aplikasi dengan `?admin=1` di akhir alamat, masukkan `ADMIN_TOKEN`, lalu unduh:

- `sessions.csv`: satu baris per sesi (kode kelas, hasil, lima rekomendasi teratas, penilaian, skor SUS)
- `answers.csv`: semua jawaban berurutan (untuk kalibrasi)

## Isi repo

| Path | Isi |
|---|---|
| `streamlit_app.py` | Tampilan aplikasi (Streamlit) |
| `crs/adaptive.py` | Kuesioner adaptif: pembaruan peluang dan pemilihan pertanyaan dengan information gain |
| `crs/service.py` | Isi halaman hasil, detail pekerjaan, dan ekspor (dipakai kedua tampilan) |
| `crs/storage.py` | Penyimpanan sesi, jawaban, dan penilaian (SQLite atau Postgres) |
| `crs/recommender.py`, `crs/questionnaire.py` | Metode baku O*NET: 60 butir dan Pearson Correlation |
| `crs/i18n/` | Terjemahan nama pekerjaan, deskripsi, kompetensi, dan aktivitas kerja |
| `data/` | Tabel O*NET hasil olahan `scripts/flatten_rdf.py` |
| `web/` | Tampilan alternatif dengan FastAPI (`.venv/bin/uvicorn web.app:app`) |
| `scripts/` | Pengolahan data dan eksperimen |
| `tests/` | Tes otomatis |

## Atribusi

Aplikasi ini memuat informasi dari O*NET 31.0 Database dan O*NET Career Exploration Tools oleh
U.S. Department of Labor, Employment and Training Administration (USDOL/ETA), digunakan di bawah
lisensi CC BY 4.0 dan O*NET Tools Developer License. O*NET® adalah merek dagang USDOL/ETA.
Pengembang aplikasi ini telah mengubah sebagian informasi tersebut. USDOL/ETA tidak menyetujui,
mendukung, atau menguji perubahan ini.
