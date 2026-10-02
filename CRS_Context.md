# CRS — Sistem Rekomendasi Karier Siswa SMA Berbasis O*NET

Dokumen ini adalah brief untuk melanjutkan pengembangan. Ia menggantikan
`CRS_ONET_Knowledge_Graph_PPR_Context.md` (arah lama, disimpan sebagai arsip).

Terakhir diperbarui: 2 Oktober 2026.

## 1. Tujuan

Skripsi: sistem rekomendasi karier untuk **siswa SMA**, memakai data **O*NET 31.0**.

- **Metode utama:** Content-Based Filtering dengan Pearson Correlation.
- **Metode pembanding:** Personalized PageRank (PPR) pada graph O*NET.
- Judul lama (Knowledge Graph + PPR) boleh diganti; sudah dikonfirmasi oleh pemilik proyek.

## 2. Alur sistem

```text
Kuesioner minat (60 butir)  ->  skor RIASEC (0-40 per tipe)
Pilih 3-5 bidang favorit    ->  dari 41 Specific Interest Areas O*NET
                 |
                 v
Skor tiap pekerjaan = Pearson(RIASEC siswa, RIASEC pekerjaan) + kecocokan bidang favorit
                 |
                 v
Urutkan, saring Job Zone (opsional), ambil N teratas
                 |
                 v
Per pekerjaan: label kecocokan, deskripsi, jenjang persiapan,
               kompetensi yang perlu dikembangkan, karier serupa
```

Keputusan desain:

- **Ranking hanya dari minat.** Siswa SMA belum punya kompetensi kerja, jadi kompetensi tidak
  boleh menyingkirkan pekerjaan dari rekomendasi.
- **Kompetensi hanya untuk skill gap**, yaitu daftar yang perlu dikembangkan. Kebutuhan pekerjaan =
  skala Level / 7, hanya untuk elemen dengan Importance >= 3.
- **Label kecocokan** memakai batas resmi O*NET Interest Profiler: korelasi >= 0,729 "Sangat cocok",
  >= 0,608 "Cocok", >= 0 "Cukup cocok" (Gregory & Lewis, 2016).
- **Related Occupations** dipakai sebagai "karier serupa" dan sebagai ground truth evaluasi,
  tidak sebagai masukan ranking.

## 3. Isi folder

| Path | Isi |
|---|---|
| `crs/data.py` | Memuat tabel O*NET; 878 pekerjaan dengan data lengkap |
| `crs/recommender.py` | Algoritma rekomendasi dan skill gap |
| `crs/questionnaire.py` | 60 butir Interest Profiler Short Form (terjemahan Indonesia), penghitung skor, label 41 bidang |
| `crs/adaptive.py` | Kuesioner adaptif (information gain, aturan berhenti, pemeriksaan konsistensi) |
| `crs/__main__.py` | Demo terminal: `python3 -m crs --adaptif` atau `--quiz` |
| `tests/` | 25 tes: `python3 -m unittest discover tests` |
| `scripts/flatten_rdf.py` | RDF resmi O*NET 31.0 -> CSV di `data/` |
| `scripts/experiments.py` | Uji PPR lawan similarity (reproduksi notebook lama) |
| `scripts/interest_experiment.py` | Uji pilihan input minat |
| `scripts/adaptive_questionnaire.py` | Prototipe kuesioner adaptif (information gain) dan uji biasnya |
| `scripts/adaptive_experiment.py` | Uji awal: urutan bidang adaptif lawan tetap |
| `scripts/check_ppr_bias.py` | Uji bias PPR ke PageRank global |
| `notebook/CRS_Simple.ipynb` | Prototype PPR lama (arsip, bahan pembanding) |
| `data/db_31_0_nt/` | RDF N-Triples resmi (2,5 GB) |

## 4. Fakta data O*NET 31.0 (sudah dicek ke file RDF)

- Rilis Agustus 2026; tersedia sebagai RDF (JSON-LD, N-Triples, RDF/XML, Turtle). 11,16 juta triple.
- Rating dimodelkan lewat node perantara: `Occupation -hasRating-> XRating -refersTo-> Element, Scale`.
- 1.016 pekerjaan terdaftar; 923 punya data minat; 910 punya data kompetensi; 891 punya
  Specific Interest Areas; **878 lengkap semuanya** (ini yang dipakai sistem).
- Skala: minat (OI) 1-7; Importance (IM) 1-5; Level (LV) 0-7.
- Job Zone di rilis ini ada empat: 1-2 (digabung), 3, 4, 5.
- Related Occupations: 20 per pekerjaan, 10 pertama bertingkat "Primary".

## 5. Hasil uji (siswa sintetis, bukan siswa sungguhan)

Siswa sintetis = salinan ber-noise (sd 0,10) dari profil satu pekerjaan. "Hit@10" = pekerjaan asal
masuk 10 besar. "RelRecall@10" = bagian Related Occupations primer yang masuk 10 besar. Acak = 1,1%.

Perbandingan metode (profil minat + 16 kompetensi, 910 pekerjaan):

| Metode | Hit@10 | RelRecall@10 |
|---|---|---|
| PPR mentah (prototype lama) | 3,7% | 2,9% |
| PPR dibagi skor global | 19,0% | 8,1% |
| Similarity notebook lama (mean absolute difference) | 90,2% | 23,4% |
| Cosine similarity | 92,3% | 24,9% |

Pilihan input minat (891 pekerjaan):

| Input siswa | Hit@10 | RelRecall@10 |
|---|---|---|
| RIASEC saja | 65% | 19% |
| RIASEC + 5 bidang favorit (yang dipakai sistem) | 86% | 32% |
| Menilai semua 41 bidang | 96% | 38% |

Kenapa PPR kalah: graph pekerjaan-elemen hampir lengkap (98,7% pasangan punya rating), sehingga
bentuk graph tidak membedakan pekerjaan; PPR mengikuti PageRank global (Spearman 0,7-0,9) dan
mengangkat pekerjaan yang ratingnya tinggi di semua elemen (dokter, insinyur) untuk profil apa pun.
Mengubah bobot edge, alpha, atau menambah edge Related Occupations tidak memperbaikinya.

Bug di notebook lama: `pivot_table` merata-rata skala IM dan LV; Essential Skills masuk dua kali
sebagai node; 13 pekerjaan hanya punya data minat.

## 5b. Prototipe kuesioner adaptif (belum masuk `crs/`)

Pemilik proyek ingin semua pertanyaan adaptif dan makin menggali. Prototipe: `scripts/adaptive_questionnaire.py`.

- Kolam pertanyaan dari O*NET: 60 butir Interest Profiler, 41 bidang minat, 1.991 Detailed Work Activities.
- Tiap jawaban memperbarui peluang semua pekerjaan (Bayes); tidak ada pekerjaan yang dibuang.
- Pertanyaan berikutnya dipilih dengan information gain. O*NET tidak menyediakan mekanisme adaptif; ini buatan proyek.
- Rujukan teori: van der Linden (1998), Weissman (2007), Rashid dkk. (2002), Golbandi dkk. (2011),
  Elahi dkk. (2016). Belum dibaca isinya, baru dipastikan keberadaannya.

Hasil pada 878 siswa sintetis (corong 12 butir + 6 bidang + 6 aktivitas = 24 pertanyaan):

| Uji | Hasil |
|---|---|
| Ketepatan | Hit@10 99,3%, RelRecall@10 35,3% (sistem flat: 82,2% / 30,9%; pertanyaan acak: 55,2% / 17,2%) |
| Kesesuaian dengan versi lengkap | Irisan 10 besar hanya 4,7 dari 10; peringkat 1 sama 86% |
| Jawaban keliru (dibalik) | 1 keliru: Hit@10 90,9%; 2 keliru: 76,2%; 4 keliru: 48,3%. Memperbesar sigma tidak menolong |
| Keadilan antar-kelompok | 98,6-100% di semua tipe minat dan Job Zone (sistem flat: Realistic 63,8%, Job Zone 2 67,5%) |
| Cakupan | 100% pekerjaan pernah muncul di 10 besar |
| Pertanyaan pertama | Mengganti pembuka mengubah 10 besar sedikit (irisan 7,7-9,9 dari 10) |
| Sensitivitas sigma | Ketepatan stabil pada x0,5-x1,5, tetapi isi 10 besar berubah (irisan 5-6 dari 10) |

Catatan: mode bebas (information gain memilih dari seluruh kolam) hampir tidak pernah memilih butir
Interest Profiler; tahap "12 butir" adalah batasan rancangan, bukan pilihan information gain. Angka
tahap aktivitas optimistis karena siswa sintetis dibuat menyukai aktivitas pekerjaan asalnya.
Kelemahan terbuka: peka terhadap jawaban keliru, dan angka sigma masih tebakan.

Perbaikan yang sudah diuji (`python3 scripts/adaptive_questionnaire.py perbaikan`):

1. Peluang jawaban asal-asalan di model (jawaban apa pun mungkin dengan peluang kecil).
2. Aturan berhenti: setelah 24 pertanyaan, lanjut bertanya sampai pekerjaan yang masih mungkin
   (exp entropi) <= 10, maksimal 40 pertanyaan.

Hit@10 dengan 0 / 1 / 2 / 4 jawaban dibalik:

| Pengaturan | 0 | 1 | 2 | 4 | Rata-rata pertanyaan |
|---|---|---|---|---|---|
| Tanpa perbaikan | 99,3% | 90,9% | 76,2% | 48,3% | 24 |
| Hanya peluang asal 0,10 | 98,6% | 95,0% | 89,9% | 68,1% | 24 |
| Hanya aturan berhenti | 99,9% | 95,6% | 87,6% | 65,7% | 24,5-27,8 |
| Keduanya (0,10; <= 10 kandidat; maks 40) | 100% | 99,4% | 99,1% | 95,3% | 25,0-29,2 |

Hasil hampir sama untuk peluang asal 0,05-0,20. Yang tidak membaik: irisan 10 besar dengan versi
lengkap tetap 4,7-4,9 dari 10.

## 5c. Kuesioner adaptif di paket (`crs/adaptive.py`, `python3 -m crs --adaptif`)

- Urutan bebas dengan information gain; minimal 20, maksimal 80 pertanyaan; berhenti saat pekerjaan
  yang masih mungkin (exp entropi) <= 5; peluang jawaban asal-asalan 0,10.
- Di akhir, 8 pertanyaan diulang sebagai pemeriksaan konsistensi (jawaban terkuat lebih dulu).
  Pertanyaan ulang tidak mengubah hasil.
- Keluaran `Session.outcome`: `jelas`, `beragam` (menyukai >= 90% pertanyaan, atau mencapai batas
  dengan cukup banyak "suka"), `belum_jelas` (mencapai batas, hampir tidak ada yang disukai),
  `tidak_konsisten` (rata-rata perubahan jawaban ulang > 1,25 langkah).
- Simulasi pemeriksaan konsistensi: menandai 89% penjawab acak, 70% yang separuh jawabannya acak,
  0% siswa konsisten, 12% siswa agak berisik, 39% siswa sangat berisik.
- Peluang hasil tidak ditampilkan ke siswa karena modelnya terlalu yakin (peringkat 1 mendekati 100%).
- Semua ambang (20, 80, 5, 0,10, 90%, 1,25, sigma) berasal dari simulasi dan perlu dikalibrasi ulang
  dengan data siswa sungguhan.

## 5d. Website (`web/`)

Jalankan: `.venv/bin/uvicorn web.app:app --reload`, lalu buka http://127.0.0.1:8000
(lingkungan: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`).
Tes: `.venv/bin/python -m unittest discover tests` (36 tes; tes web dilewati tanpa FastAPI).

- `web/app.py`: API FastAPI. `POST /api/sessions`, `GET /api/sessions/{id}`,
  `POST /api/sessions/{id}/answers`, `POST /api/sessions/{id}/finish`,
  `GET /api/sessions/{id}/result`, `GET /api/occupations/{kode}`.
- `web/store.py`: SQLite di `data/crs.sqlite3` (bisa diganti lewat variabel `CRS_DB`). Menyimpan kode
  sesi acak dan jawaban saja, tanpa nama. Server tidak menyimpan keadaan di memori: sesi dibangun
  ulang dari jawaban tersimpan pada tiap permintaan.
- `web/static/`: halaman tunggal tanpa kerangka (pembuka, pertanyaan, hasil, detail pekerjaan).
- Pekerjaan terdepan dan jumlah kandidat tidak ditampilkan ke siswa selama mengisi, supaya tidak
  memengaruhi jawaban.
- Baru berjalan lokal. Belum ada: pemasangan ke internet dan halaman admin/ekspor data.

## 5e. Terjemahan (`crs/i18n/`)

Semua teks yang dilihat siswa sudah berbahasa Indonesia:

| File | Isi |
|---|---|
| `crs/i18n/pekerjaan.csv` | 878 nama dan deskripsi pekerjaan |
| `crs/i18n/kompetensi.csv` | 119 nama kompetensi (abilities, skills, knowledge) |
| `crs/i18n/aktivitas.csv` | 1.991 aktivitas kerja (pertanyaan tahap menggali) |

- File CSV adalah sumber utama dan boleh dikoreksi langsung; teks yang kosong kembali ke bahasa Inggris.
- Terjemahan dibuat untuk proyek ini dan **belum divalidasi** ahli bahasa, guru BK, atau praktisi bidang.
- Deskripsi pekerjaan yang panjang diringkas; kalimat klasifikasi "Excludes ..." dibuang.
- Nama pekerjaan mengikuti pekerjaan Amerika; sebagian tidak punya padanan lazim di Indonesia
  (misalnya Nurse Practitioners, Physician Assistants). Nama asli O*NET tampil di halaman detail.
- "English Language" diterjemahkan harfiah menjadi "Bahasa Inggris".

## 6. Yang belum ada

1. **Uji ke siswa SMA sungguhan** dan penilaian guru BK. Semua angka di atas dari siswa sintetis.
2. **Validasi terjemahan kuesioner.** Terjemahan dibuat untuk proyek ini dan belum divalidasi;
   lisensi O*NET Tools Developer meminta validasi sebelum dirilis.
3. **Validasi terjemahan** nama pekerjaan, deskripsi, kompetensi, dan aktivitas kerja (bagian 5e).
4. **Pemasangan website ke internet.** Website sudah ada (bagian 5d) tetapi baru berjalan lokal.

## 7. Aturan untuk yang melanjutkan

- Jangan mengklaim sistem ini akurat untuk siswa nyata; yang ada baru uji konsistensi.
- Jangan menjadikan PPR metode utama lagi tanpa hasil uji baru yang mengalahkan tabel di bagian 5.
- Jangan memakai Related Occupations sebagai masukan ranking, karena ia ground truth evaluasi.
- Setiap perubahan algoritma harus tetap lulus `tests/test_recommender.py`.
- Sumber data adalah RDF resmi lewat `scripts/flatten_rdf.py`, bukan CSV buatan tangan.

## 8. Rujukan

- O*NET 31.0 Database: https://www.onetcenter.org/database.html
- Data dictionary RDF: https://www.onetcenter.org/dictionary/31.0/nt/
- Interest Profiler: https://www.onetcenter.org/IP.html
- Butir Short Form (Lampiran B): https://www.onetcenter.org/dl_files/IPSF_PP.pdf
- Metode pencocokan resmi (Gregory & Lewis, 2016): https://www.onetcenter.org/dl_files/Mini-IP_Linking.pdf
- Lisensi kuesioner: https://www.onetcenter.org/license_toolsdev.html
