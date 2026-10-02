> **ARSIP (2 Oktober 2026).** Dokumen ini menggambarkan arah lama (PPR sebagai metode utama) dan sudah digantikan oleh `CRS_Context.md`.

# CRS — O*NET Knowledge Graph + Personalized PageRank

## 1. Tujuan Dokumen

Dokumen ini adalah context/brief untuk model AI berikutnya yang akan melanjutkan pengembangan **Career Recommendation System (CRS)**.

Model harus memahami bahwa proyek ini bukan sekadar mencari pekerjaan yang memiliki nilai similarity tertinggi. Pendekatan utama yang sedang dibangun adalah:

> **Sistem Eksplorasi Bakat dan Rekomendasi Karier Berbasis Knowledge Graph O*NET dengan Personalized PageRank**

Komponen utama:

1. Student Assessment
2. Student Profile
3. O*NET 31.0 Knowledge Graph
4. Personalization Vector
5. Personalized PageRank (PPR)
6. Career/Occupation Ranking
7. Career Detail
8. Skill Gap
9. Similarity-based method sebagai baseline pembanding

---

# 2. Konsep Utama

## 2.1 O*NET

O*NET adalah sumber data/domain knowledge tentang pekerjaan (occupations).

O*NET tidak hanya menyimpan nama pekerjaan. O*NET menyediakan berbagai karakteristik pekerjaan, antara lain:

- Occupations
- Career Interests / RIASEC
- Abilities
- Essential Skills
- Transferable Skills
- Knowledge
- Work Activities
- Tasks
- Work Styles
- Work Context
- Education
- Job Zones
- Training and Experience
- Job Titles
- Related Occupations

O*NET 31.0 juga menyediakan representasi RDF Knowledge Graph resmi.

Format RDF yang tersedia mencakup:
- JSON-LD
- N-Triples
- RDF/XML
- Turtle

Dalam tahap final proyek, **RDF Knowledge Graph resmi O*NET 31.0 harus menjadi sumber graph utama**.

---

# 3. Apa yang dimaksud Occupation?

`Occupation` berarti jenis pekerjaan/profesi.

Contoh:

- Physicists
- Software Developers
- Civil Engineers
- Graphic Designers
- Registered Nurses

Dalam sistem ini:

- Student = pengguna sistem
- Occupation = target yang akan direkomendasikan/ranking
- Career = konteks jalur karier secara umum

Secara teknis, Personalized PageRank menghasilkan ranking terhadap **O*NET occupations**.

---

# 4. Knowledge Graph

Knowledge Graph digunakan untuk merepresentasikan hubungan antar-entitas O*NET.

Secara konseptual:

```text
Occupation
    |
    +---- Career Interest / RIASEC
    |
    +---- Abilities
    |
    +---- Essential Skills
    |
    +---- Transferable Skills
    |
    +---- Knowledge
    |
    +---- Work Activities
    |
    +---- Tasks
    |
    +---- Work Styles
    |
    +---- Work Context
    |
    +---- Education
    |
    +---- Job Zone
```

Contoh konseptual:

```text
Physicists
    |
    +---- Investigative
    +---- Realistic
    +---- Mathematical Reasoning
    +---- Critical Thinking
    +---- Programming
    +---- Physics Knowledge
    +---- Research Activities
    +---- Scientific Tasks
```

Relasi dan struktur sebenarnya harus mengikuti RDF resmi O*NET, bukan dibuat berdasarkan asumsi.

---

# 5. Mengapa Menggunakan Knowledge Graph?

Pendekatan similarity biasa membandingkan:

```text
Student Profile
      |
      v
Occupation Profile
      |
      v
Similarity Score
```

Sedangkan Knowledge Graph memungkinkan sistem mempertimbangkan struktur hubungan:

```text
Student
   |
   +--> Investigative
   |
   +--> Programming
   |
   +--> Critical Thinking
             |
             v
        O*NET Graph
             |
       +-----+------+
       |            |
       v            v
 Occupation A   Occupation B
       |            |
       v            v
 Knowledge      Activities
 Skills         Tasks
```

Jadi rekomendasi tidak hanya bergantung pada jarak numerik antar-vector, tetapi pada posisi dan hubungan entitas dalam graph.

---

# 6. Student Assessment

Sistem menerima hasil assessment siswa.

Contoh RIASEC:

```python
student_riasec = {
    "Realistic": 0.65,
    "Investigative": 0.90,
    "Artistic": 0.40,
    "Social": 0.50,
    "Enterprising": 0.35,
    "Conventional": 0.60
}
```

Contoh kompetensi:

```python
student_competency = {
    "Deductive Reasoning": 0.85,
    "Inductive Reasoning": 0.80,
    "Mathematical Reasoning": 0.75,
    "Critical Thinking": 0.90,
    "Complex Problem Solving": 0.85,
    "Systems Analysis": 0.80,
    "Programming": 0.85,
    "Technology Design": 0.80
}
```

Nilai tersebut menjadi representasi profil siswa.

---

# 7. Personalization Vector

Profil siswa kemudian digunakan sebagai personalization vector untuk Personalized PageRank.

Secara konsep:

```text
Student Assessment
        |
        v
Student Profile
        |
        v
Personalization Vector
        |
        v
O*NET Knowledge Graph
```

Node yang relevan dengan profil siswa mendapatkan bobot personalization.

Contoh:

```text
Investigative        -> tinggi
Programming          -> tinggi
Critical Thinking    -> tinggi
Systems Analysis     -> tinggi
Artistic             -> rendah
```

Nilai tersebut tidak berarti probabilitas menjadi suatu pekerjaan.

Nilai tersebut menunjukkan seberapa kuat node tersebut menjadi titik awal personalisasi PageRank.

---

# 8. Personalized PageRank

Personalized PageRank adalah algoritma ranking utama.

Tujuannya adalah memberikan skor lebih tinggi kepada node yang secara struktural lebih dekat/terhubung dengan node yang diprioritaskan oleh profil siswa.

Alur:

```text
Student Profile
      |
      v
Personalization Vector
      |
      v
O*NET Knowledge Graph
      |
      v
Personalized PageRank
      |
      v
Occupation Scores
      |
      v
Occupation Ranking
```

Parameter prototype yang sudah digunakan:

```python
alpha = 0.85
```

`alpha=0.85` merupakan parameter awal/konvensional untuk eksperimen, bukan hasil optimasi atau klaim bahwa nilai tersebut paling optimal.

---

# 9. Cara Kerja PPR Secara Intuitif

Misalnya seorang siswa memiliki:

```text
Investigative       0.90
Programming         0.85
Critical Thinking   0.90
Systems Analysis    0.80
```

Graph mungkin memiliki hubungan:

```text
Investigative
     |
     +-------- Physicists
     |
     +-------- Software Developers
     |
     +-------- Research Scientists


Programming
     |
     +-------- Software Developers
     |
     +-------- Robotics Engineers
     |
     +-------- Physicists
```

PPR menyebarkan importance melalui hubungan graph.

Career/occupation yang memiliki hubungan kuat dengan banyak karakteristik relevan dapat memperoleh skor PageRank lebih tinggi.

Penting:

> PPR Score bukan persentase kecocokan, bukan probabilitas diterima kerja, dan bukan probabilitas sukses dalam karier.

PPR Score digunakan untuk **ranking**.

---

# 10. Career Ranking

Setelah PPR selesai, hanya node bertipe `occupation` yang diambil untuk ranking.

Contoh:

```text
Rank   Occupation
------------------------------
1      Physicists
2      Robotics Engineers
3      Manufacturing Engineers
4      Bioengineers
5      Marine Engineers
```

Sistem kemudian mengambil informasi tambahan dari O*NET untuk career detail.

---

# 11. Career Detail

Untuk occupation yang dipilih, sistem dapat menampilkan:

```text
Occupation
    |
    +-- Title
    +-- O*NET-SOC Code
    +-- Description
    +-- Abilities
    +-- Skills
    +-- Knowledge
    +-- Tasks
    +-- Work Activities
    +-- Education
    +-- Job Zone
    +-- Work Styles
    +-- Work Context
```

Contoh:

```text
Physicists
O*NET-SOC Code: 19-2012.00

Description:
Conduct research into physical phenomena, develop theories
on the basis of observation and experiments, and devise
methods to apply physical laws and theories.
```

---

# 12. Skill Gap

Setelah occupation direkomendasikan, sistem membandingkan kompetensi siswa dengan requirement occupation.

Konsep:

```text
Student Level
       |
       | compare
       v
Occupation Requirement
       |
       v
Skill Gap
```

Secara sederhana:

```text
Gap = max(Occupation Requirement - Student Level, 0)
```

Contoh:

```text
Mathematical Reasoning
Student       : 0.75
Occupation    : 0.768
Gap           : 0.018
```

Skill gap digunakan untuk memberikan informasi pengembangan diri, bukan untuk menyatakan siswa tidak cocok.

---

# 13. Data O*NET yang Direncanakan Digunakan

## Utama

### Occupation
Digunakan sebagai target recommendation.

### Career Interest / RIASEC
Digunakan untuk merepresentasikan minat siswa dan hubungan occupation-interest.

### Abilities
Contoh:
- Deductive Reasoning
- Inductive Reasoning
- Mathematical Reasoning
- Oral Comprehension
- Written Expression

### Essential Skills
Contoh:
- Critical Thinking
- Active Listening
- Reading Comprehension
- Speaking

### Transferable Skills
Contoh:
- Complex Problem Solving
- Programming
- Systems Analysis
- Systems Evaluation
- Technology Design
- Social Perceptiveness
- Service Orientation

### Knowledge
Contoh:
- Mathematics
- Physics
- Computers and Electronics
- Medicine
- Engineering and Technology

Knowledge dapat memperkaya graph dan jalur propagasi walaupun tidak semua Knowledge feature harus langsung digunakan sebagai personalization input siswa.

### Work Activities
Memberikan konteks aktivitas pekerjaan.

### Tasks
Memberikan detail pekerjaan.

### Education / Job Zone
Digunakan untuk career detail dan informasi persiapan.

---

# 14. Data yang Bisa Ditambahkan Kemudian

Tidak semua data harus masuk ke MVP.

Data tambahan:

- Work Styles
- Work Context
- Training and Experience
- Related Occupations
- Job Titles
- Illustrative Activities
- Career Interest Type Keywords

Data tersebut dapat digunakan setelah graph dasar dan PPR berhasil.

Prinsip:

> Jangan memasukkan semua data hanya karena tersedia.

Data harus dimasukkan jika mempunyai fungsi jelas terhadap recommendation atau career explanation.

---

# 15. Graph Resmi vs Graph Prototype

Sebelumnya sudah dibuat prototype:

```text
O*NET CSV
   |
   v
Pandas
   |
   v
Manual Graph Construction
   |
   v
NetworkX
   |
   v
Personalized PageRank
```

Prototype tersebut sudah menghasilkan:

```text
Nodes : 1,059
Edges : 247,676
```

Prototype tetap dipertahankan sebagai baseline dan pembelajaran.

Namun pendekatan utama berikutnya adalah:

```text
O*NET 31.0 RDF
       |
       v
Official O*NET Knowledge Graph
       |
       v
Relevant Subgraph
       |
       v
Personalization
       |
       v
Personalized PageRank
       |
       v
Occupation Ranking
```

Jangan menganggap graph manual sebelumnya sebagai graph resmi O*NET.

---

# 16. Mengapa Tidak Langsung Menggunakan Seluruh RDF?

O*NET Knowledge Graph sangat besar.

Sistem tidak perlu memasukkan seluruh entitas RDF ke dalam algoritma PPR tanpa seleksi.

Pendekatan yang direncanakan:

```text
Official O*NET RDF
        |
        v
Identify relevant entities/relations
        |
        v
Build/use relevant subgraph
        |
        v
Personalized PageRank
```

Subgraph awal harus fokus pada relasi yang relevan dengan recommendation:

```text
Occupation
    |
    +-- Career Interest
    +-- Abilities
    +-- Essential Skills
    +-- Transferable Skills
    +-- Knowledge
    +-- Work Activities
```

Tasks, Work Context, Education, dan data lain dapat digunakan untuk enrichment/detail setelah recommendation core berjalan.

---

# 17. Baseline Similarity

Similarity-based recommendation tetap dipertahankan sebagai baseline.

Baseline yang sudah dibuat menggunakan:

```text
Interest Fit
      +
Competency Fit
      |
      v
Overall Similarity
```

Kemudian dibandingkan dengan PPR.

Tujuannya bukan untuk menyatakan PPR pasti lebih akurat.

Perbandingan digunakan untuk melihat apakah dua pendekatan menghasilkan ranking yang berbeda.

Contoh hasil sebelumnya:

```text
PPR Top 10
vs
Similarity Top 10

Shared careers = 2
Overlap@10 = 20%
```

Interpretasi yang benar:

> Kedua metode menghasilkan ranking yang cukup berbeda karena mekanisme perhitungannya berbeda.

Jangan menyimpulkan PPR lebih baik hanya berdasarkan overlap tersebut.

Untuk klaim akurasi diperlukan ground truth/evaluation dataset.

---

# 18. Hasil Eksperimen yang Sudah Ada

Prototype PPR sudah diuji menggunakan beberapa profil siswa.

Profil berbeda menghasilkan ranking berbeda.

Contoh:

```text
Investigative Technical
1. Physicists
2. Robotics Engineers
3. Manufacturing Engineers
...


Artistic Social
1. Architecture Teachers, Postsecondary
2. Anesthesiologists
3. Ophthalmologists
...


Realistic Technical
1. Robotics Engineers
2. Physicists
3. Manufacturing Engineers
```

Hal ini menunjukkan personalization memang memengaruhi ranking.

Tetapi ini belum membuktikan akurasi dunia nyata.

---

# 19. Arsitektur Konseptual Final

```text
┌─────────────────────────────────────────────┐
│              STUDENT ASSESSMENT             │
│                                             │
│ RIASEC + Abilities + Skills + Knowledge     │
└──────────────────────┬──────────────────────┘
                       |
                       v
              ┌────────────────┐
              │ Student Profile │
              └───────┬────────┘
                      |
                      v
           ┌──────────────────────┐
           │ Personalization      │
           │ Vector               │
           └──────────┬───────────┘
                      |
                      v
┌─────────────────────────────────────────────┐
│          O*NET 31.0 RDF KNOWLEDGE GRAPH     │
│                                             │
│ Occupation                                  │
│    ↕                                        │
│ Career Interest                             │
│    ↕                                        │
│ Abilities                                   │
│    ↕                                        │
│ Essential Skills                            │
│    ↕                                        │
│ Transferable Skills                         │
│    ↕                                        │
│ Knowledge                                   │
│    ↕                                        │
│ Work Activities / Tasks                    │
└──────────────────────┬──────────────────────┘
                       |
                       v
              ┌────────────────┐
              │ Personalized   │
              │ PageRank       │
              └───────┬────────┘
                      |
                      v
              ┌────────────────┐
              │ Occupation     │
              │ Ranking        │
              └───────┬────────┘
                      |
             ┌────────┴────────┐
             v                 v
      Career Detail        Skill Gap
             |                 |
             └────────┬────────┘
                      v
              Career Recommendation
```

---

# 20. Teknologi

Tahap penelitian/prototype:

```text
Python
Pandas
NetworkX
RDF parser/library yang sesuai
Google Colab
O*NET 31.0 RDF
```

Tahap aplikasi:

```text
Python
FastAPI
SQLite/PostgreSQL
Frontend
```

Neo4j tidak wajib untuk tahap awal.

Jangan menambahkan teknologi hanya untuk membuat arsitektur terlihat lebih kompleks.

---

# 21. Urutan Pengerjaan Berikutnya

Model berikutnya harus melanjutkan dengan urutan:

### Step 1
Ambil O*NET 31.0 RDF resmi.

### Step 2
Pelajari struktur RDF:
- classes
- entities
- predicates/relations
- occupation identifiers
- rating relationships

### Step 3
Ambil satu occupation sebagai contoh dan trace relasinya.

Contoh:

```text
Physicists
   |
   +--> Interest
   +--> Ability
   +--> Skill
   +--> Knowledge
   +--> Work Activity
```

### Step 4
Tentukan subgraph yang relevan untuk recommendation.

### Step 5
Bangun/load graph di Python.

### Step 6
Hubungkan Student Profile dengan personalization vector.

### Step 7
Jalankan Personalized PageRank.

### Step 8
Ambil occupation nodes dan ranking.

### Step 9
Ambil detail occupation.

### Step 10
Hitung skill gap.

### Step 11
Bandingkan hasil dengan similarity baseline.

### Step 12
Baru setelah core algorithm stabil, pindahkan implementation dari Colab ke VS Code/FastAPI.

---

# 22. Hal yang Jangan Dilakukan

Model berikutnya jangan:

1. Menganggap PPR sebagai machine learning supervised.
2. Menganggap PPR Score sebagai probability.
3. Mengklaim PPR lebih akurat tanpa ground truth.
4. Menggunakan seluruh O*NET RDF tanpa alasan.
5. Membuat relasi graph berdasarkan tebakan jika relasi resmi O*NET tersedia.
6. Mengganti Knowledge Graph dengan similarity matrix.
7. Menganggap O*NET sebagai algoritma.
8. Menganggap Knowledge Graph sebagai algoritma.
9. Menggunakan Neo4j hanya karena proyek disebut Knowledge Graph.
10. Langsung membuat API sebelum graph + PPR tervalidasi.

---

# 23. Terminologi yang Harus Konsisten

| Istilah | Arti |
|---|---|
| O*NET | Sumber knowledge/data pekerjaan |
| Occupation | Jenis pekerjaan/profesi |
| Knowledge Graph | Representasi entitas dan hubungan O*NET |
| RDF | Format representasi graph resmi O*NET |
| Student Profile | Representasi hasil assessment siswa |
| Personalization Vector | Bobot awal yang merepresentasikan profil siswa |
| Personalized PageRank | Algoritma ranking berbasis graph |
| PPR Score | Skor ranking PageRank, bukan probabilitas |
| Career Ranking | Urutan occupation berdasarkan PPR |
| Skill Gap | Perbedaan requirement occupation dengan level siswa |
| Similarity | Baseline pembanding |

---

# 24. Status Saat Ini

Sudah selesai:

- O*NET 31.0 CSV berhasil diproses.
- RIASEC profile berhasil dibuat.
- Competency profiles berhasil dibuat.
- Prototype Knowledge Graph NetworkX berhasil dibuat.
- Personalization vector berhasil dibuat.
- Personalized PageRank berhasil dijalankan.
- Career ranking berhasil.
- Career detail berhasil.
- Skill gap berhasil.
- Multiple student profiles berhasil diuji.
- Similarity baseline berhasil.
- PPR vs similarity comparison berhasil.

Yang akan dikerjakan:

> **Menguji dan mengimplementasikan pendekatan menggunakan O*NET 31.0 RDF Knowledge Graph resmi.**

Jangan langsung menghapus prototype NetworkX sebelumnya. Gunakan sebagai baseline dan pembanding.

---

# 25. Inti Proyek dalam Satu Kalimat

> Sistem menerima profil minat dan kompetensi siswa, menggunakan profil tersebut untuk mempersonalisasi navigasi pada Knowledge Graph resmi O*NET 31.0, kemudian menggunakan Personalized PageRank untuk meranking occupation yang paling relevan dan menghasilkan career detail serta skill gap.

