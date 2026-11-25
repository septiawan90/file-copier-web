# Local File Finder & Copier (Web Lokal)

Aplikasi web lokal berbasis **Python 3 (Standard Library)** + **HTML/CSS/JS** untuk mencari, menyaring, mem-preview, dan menyalin/memindahkan file lokal di Windows tanpa instalasi library eksternal (`pip`).

## Fitur Utama & Fitur Tambahan
1. **Browse Folder Sumber & Tujuan**: Jelajahi drive (`C:\`, `D:\`, dst.) langsung dari browser atau buka folder tujuan di File Explorer.
2. **Filter Lengkap**:
   - Kata kunci nama file (multi kata kunci dipisah koma, atau mode Regex).
   - Filter ekstensi (`.pdf`, `.docx`, `.txt`, `.jpeg`, dll.).
   - Filter tanggal berbasis **Dibuat (`CreationTime`)**, **Diubah (`LastWriteTime`)**, atau **Dibuat ATAU Diubah**.
   - Mode **Multi-tanggal tertentu** (mis. `2026-11-17, 2026-11-25`) atau **Rentang tanggal**.
   - Opsi scan subfolder (rekursif).
3. **Tabel Preview Interaktif**:
   - Penyaringan cepat (*quick search*), pengurutan kolom, indikator jika tanggal dibuat dan diubah berbeda (`Tgl Beda`), serta seleksi checkbox.
4. **Preview Isi File**:
   - Teks (`.txt`, `.md`, `.csv`, `.json`, `.log`, dll.).
   - Dokumen Word (`.docx`) diekstrak langsung menggunakan Python `zipfile` + `xml.etree`.
   - Gambar (`.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`).
   - Dokumen `.pdf` langsung di browser.
5. **Kebijakan Konflik & Mode Transfer**:
   - Pilih **Copy** atau **Move**, serta penanganan file duplikat: **Lewati (Skip)**, **Ganti Nama Otomatis**, atau **Timpa (Overwrite)**.
6. **Preset Filter Tersimpan**:
   - Dilengkapi preset bawaan (*File Notulensi* & *Download 17 & 25 Nov 2026*) dan kemampuan simpan/hapus preset ke `presets.json`.

## Cara Menjalankan
Pastikan Python 3 sudah terpasang pada PATH Windows, lalu jalankan dari folder `D:\tes5\file-copier-web`:

```bat
python app.py
```

Atau klik dua kali file `run.bat`. Aplikasi akan terbuka di `http://127.0.0.1:8765`.
