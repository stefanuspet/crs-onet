"""Interest questionnaire: the 60 items of the O*NET Interest Profiler Short Form, in Indonesian.

Each item is a work activity. The student answers on a five-point scale
(0 = sangat tidak suka ... 4 = sangat suka). The score of a RIASEC type is the sum of
its 10 items, so every type ranges from 0 to 40.

The Indonesian wording is an unvalidated translation made for this project. The O*NET Tools
Developer License asks that adapted versions be validated for their audience before release:
https://www.onetcenter.org/license_toolsdev.html

Attribution required by that license:
    This application includes information from the O*NET Career Exploration Tools by the
    U.S. Department of Labor, Employment and Training Administration (USDOL/ETA). Used under
    the O*NET Tools Developer License. O*NET(R) is a trademark of USDOL/ETA. The author has
    modified all or some of this information. USDOL/ETA has not approved, endorsed, or tested
    these modifications.
"""
from dataclasses import dataclass

from .data import RIASEC

RESPONSES = ["Sangat tidak suka", "Tidak suka", "Ragu-ragu", "Suka", "Sangat suka"]  # scored 0..4
INSTRUCTION = ("Bayangkan kamu melakukan kegiatan berikut sebagai pekerjaan. Seberapa suka kamu melakukannya? "
               "Jangan pikirkan pendidikan yang dibutuhkan atau besar penghasilannya.")

_ITEMS = {
    "Realistic": [
        ("Build kitchen cabinets", "Membuat lemari dapur"),
        ("Lay brick or tile", "Memasang batu bata atau ubin"),
        ("Repair household appliances", "Memperbaiki peralatan rumah tangga"),
        ("Raise fish in a fish hatchery", "Membudidayakan ikan di tempat pembenihan"),
        ("Assemble electronic parts", "Merakit komponen elektronik"),
        ("Drive a truck to deliver packages to offices and homes",
         "Mengemudikan truk untuk mengantar paket ke kantor dan rumah"),
        ("Test the quality of parts before shipment", "Menguji kualitas komponen sebelum dikirim"),
        ("Repair and install locks", "Memperbaiki dan memasang kunci"),
        ("Set up and operate machines to make products", "Menyiapkan dan mengoperasikan mesin untuk membuat produk"),
        ("Put out forest fires", "Memadamkan kebakaran hutan"),
    ],
    "Investigative": [
        ("Develop a new medicine", "Mengembangkan obat baru"),
        ("Study ways to reduce water pollution", "Meneliti cara mengurangi pencemaran air"),
        ("Conduct chemical experiments", "Melakukan percobaan kimia"),
        ("Study the movement of planets", "Mempelajari pergerakan planet"),
        ("Examine blood samples using a microscope", "Memeriksa sampel darah dengan mikroskop"),
        ("Investigate the cause of a fire", "Menyelidiki penyebab kebakaran"),
        ("Develop a way to better predict the weather", "Mengembangkan cara memprakirakan cuaca yang lebih akurat"),
        ("Work in a biology lab", "Bekerja di laboratorium biologi"),
        ("Invent a replacement for sugar", "Menciptakan bahan pengganti gula"),
        ("Do laboratory tests to identify diseases", "Melakukan uji laboratorium untuk mengenali penyakit"),
    ],
    "Artistic": [
        ("Write books or plays", "Menulis buku atau naskah drama"),
        ("Play a musical instrument", "Memainkan alat musik"),
        ("Compose or arrange music", "Menggubah atau mengaransemen musik"),
        ("Draw pictures", "Menggambar"),
        ("Create special effects for movies", "Membuat efek khusus untuk film"),
        ("Paint sets for plays", "Melukis dekorasi panggung untuk pertunjukan drama"),
        ("Write scripts for movies or television shows", "Menulis naskah film atau acara televisi"),
        ("Perform jazz or tap dance", "Menampilkan tari jazz atau tap dance"),
        ("Sing in a band", "Bernyanyi dalam sebuah band"),
        ("Edit movies", "Menyunting film"),
    ],
    "Social": [
        ("Teach an individual an exercise routine", "Mengajari seseorang rangkaian latihan olahraga"),
        ("Help people with personal or emotional problems",
         "Membantu orang yang memiliki masalah pribadi atau emosional"),
        ("Give career guidance to people", "Memberikan bimbingan karier kepada orang lain"),
        ("Perform rehabilitation therapy", "Melakukan terapi rehabilitasi"),
        ("Do volunteer work at a non-profit organization", "Menjadi relawan di organisasi nirlaba"),
        ("Teach children how to play sports", "Mengajari anak-anak berolahraga"),
        ("Teach sign language to people who are deaf or hard of hearing",
         "Mengajarkan bahasa isyarat kepada orang tuli atau yang mengalami gangguan pendengaran"),
        ("Help conduct a group therapy session", "Membantu memandu sesi terapi kelompok"),
        ("Take care of children at a day-care center", "Mengasuh anak-anak di tempat penitipan anak"),
        ("Teach a high-school class", "Mengajar di kelas SMA"),
    ],
    "Enterprising": [
        ("Buy and sell stocks and bonds", "Membeli dan menjual saham dan obligasi"),
        ("Manage a retail store", "Mengelola toko ritel"),
        ("Operate a beauty salon or barber shop", "Menjalankan usaha salon kecantikan atau pangkas rambut"),
        ("Manage a department within a large company", "Memimpin sebuah departemen di perusahaan besar"),
        ("Start your own business", "Memulai usaha sendiri"),
        ("Negotiate business contracts", "Menegosiasikan kontrak bisnis"),
        ("Represent a client in a lawsuit", "Mewakili klien dalam perkara hukum"),
        ("Market a new line of clothing", "Memasarkan lini pakaian baru"),
        ("Sell merchandise at a department store", "Menjual barang di toserba"),
        ("Manage a clothing store", "Mengelola toko pakaian"),
    ],
    "Conventional": [
        ("Develop a spreadsheet using computer software",
         "Membuat lembar kerja (spreadsheet) dengan perangkat lunak komputer"),
        ("Proofread records or forms", "Memeriksa ketepatan catatan atau formulir"),
        ("Install software across computers on a large network",
         "Memasang perangkat lunak pada komputer-komputer dalam jaringan besar"),
        ("Operate a calculator", "Mengoperasikan kalkulator"),
        ("Keep shipping and receiving records", "Mencatat pengiriman dan penerimaan barang"),
        ("Calculate the wages of employees", "Menghitung gaji karyawan"),
        ("Inventory supplies using a hand-held computer", "Mendata persediaan barang dengan perangkat genggam"),
        ("Record rent payments", "Mencatat pembayaran sewa"),
        ("Keep inventory records", "Mengelola catatan persediaan barang"),
        ("Stamp, sort, and distribute mail for an organization",
         "Mencap, menyortir, dan membagikan surat untuk sebuah organisasi"),
    ],
}

# Indonesian labels for O*NET's 41 Specific Interest Areas (the "pilih bidang favorit" question).
AREA_LABELS = {
    "Accounting": "Akuntansi",
    "Agriculture": "Pertanian",
    "Animal Service": "Perawatan Hewan",
    "Applied Arts and Design": "Seni Terapan dan Desain",
    "Athletics": "Olahraga",
    "Business Initiatives": "Kewirausahaan",
    "Construction/Woodwork": "Konstruksi dan Pertukangan Kayu",
    "Creative Writing": "Penulisan Kreatif",
    "Culinary Art": "Seni Kuliner",
    "Engineering": "Teknik (Rekayasa)",
    "Finance": "Keuangan",
    "Health Care Service": "Layanan Kesehatan",
    "Human Resources": "Sumber Daya Manusia",
    "Humanities": "Humaniora",
    "Information Technology": "Teknologi Informasi",
    "Law": "Hukum",
    "Life Science": "Ilmu Hayati",
    "Management/Administration": "Manajemen dan Administrasi",
    "Marketing/Advertising": "Pemasaran dan Periklanan",
    "Mathematics/Statistics": "Matematika dan Statistika",
    "Mechanics/Electronics": "Mekanika dan Elektronika",
    "Media": "Media",
    "Medical Science": "Ilmu Kedokteran",
    "Music": "Musik",
    "Nature/Outdoors": "Alam dan Kegiatan Luar Ruang",
    "Office Work": "Pekerjaan Kantor",
    "Performing Arts": "Seni Pertunjukan",
    "Personal Service": "Layanan Pribadi",
    "Physical Science": "Ilmu Fisika dan Kimia",
    "Physical/Manual Labor": "Pekerjaan Fisik",
    "Politics": "Politik",
    "Professional Advising": "Konsultasi Profesional",
    "Protective Service": "Keamanan dan Perlindungan",
    "Public Speaking": "Berbicara di Depan Umum",
    "Religious Activities": "Kegiatan Keagamaan",
    "Sales": "Penjualan",
    "Social Science": "Ilmu Sosial",
    "Social Service": "Layanan Sosial",
    "Teaching/Education": "Pengajaran dan Pendidikan",
    "Transportation/Machine Operation": "Transportasi dan Pengoperasian Mesin",
    "Visual Arts": "Seni Rupa",
}


@dataclass(frozen=True)
class Item:
    number: int   # 1..60, the order in which items are shown
    riasec: str
    text_en: str
    text_id: str


def items():
    """The 60 items, interleaved so that consecutive items come from different RIASEC types."""
    result = []
    for position in range(10):
        for riasec in RIASEC:
            en, idn = _ITEMS[riasec][position]
            result.append(Item(len(result) + 1, riasec, en, idn))
    return result


def score(answers):
    """answers: {item number: 0..4} for all 60 items -> {RIASEC type: 0..40}."""
    all_items = items()
    missing = [it.number for it in all_items if it.number not in answers]
    if missing:
        raise ValueError(f"Butir belum dijawab: {missing}")
    totals = dict.fromkeys(RIASEC, 0)
    for it in all_items:
        value = answers[it.number]
        if value not in range(len(RESPONSES)):
            raise ValueError(f"Jawaban butir {it.number} harus 0..{len(RESPONSES) - 1}, bukan {value!r}")
        totals[it.riasec] += value
    if len(set(totals.values())) == 1:
        # Same rule as the official profiler: a flat profile carries no information about interests.
        raise ValueError("Semua skor minat sama, sehingga profil tidak bisa dicocokkan. Coba isi ulang kuesioner.")
    return totals
