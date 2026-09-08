# Dashboard - Setup Guide

## How it works
This folder lives in a shared Google Drive and syncs automatically.
When new tools are added, they appear on your device without any action from you.

---

## First time on a new device

### Step 1 — Install Python (once ever)
Download **Python 3.11 or 3.12** from:
**https://www.python.org/downloads/**

> During installation, tick **"Add python.exe to PATH"**

Recommended: **3.12** (best package support on Windows).
Avoid Python 3.14+ if install fails — some libraries may not have Windows wheels yet.

---

### Step 2 — Install Google Drive for Desktop (once ever)
Download from: **https://drive.google.com/drive/download**

Sign in with the Google account this folder was shared with.
The DASHBOARD folder will appear on your computer automatically.

---

### Step 3 — Run setup (once per device)
Inside the DASHBOARD folder, double-click **`setup.bat`**

This installs all required libraries. Takes a few minutes.
You only need to do this once per device (or again if new libraries are added).

---

### Step 4 — Create a Desktop shortcut (once per device)
Double-click **`create_shortcut.bat`**

This places a **Dashboard** shortcut on your Desktop.

---

## Opening the dashboard (every day)
Double-click the **Dashboard** shortcut on your Desktop, or **`run.bat`**.

---

## Getting updates
Google Drive syncs changes automatically. Open `run.bat` as usual.

If a new tool needs a new library, run **`setup.bat`** once more.

---

## Folder structure
```
DASHBOARD/
├── dashboard.py                 ← Main app
├── run.bat                      ← Open the dashboard
├── setup.bat                    ← First-time setup
├── create_shortcut.bat          ← Desktop shortcut
├── requirements.txt             ← Core libraries
├── requirements-optional.txt    ← Optional AI packages (rembg)
├── scripts/                     ← Tool scripts
├── scan_letter/                 ← Scan workflow tools
├── paras_print_scripts/         ← Paras Print tools
└── samples/                     ← Sample files
```

---

## Trouble?

| Error | Fix |
|--------|-----|
| **Python not found** | Install Python 3.11/3.12 from python.org and tick **Add to PATH**, then close and reopen the setup window |
| **Module not found** | Run `setup.bat` again |
| **pip / t64.exe / distlib error** | Already fixed in latest `setup.bat` (it no longer upgrades pip). Sync the folder and re-run `setup.bat` |
| **pip / wheel build failed** | Use Python **3.12** (not 3.14). Re-run `setup.bat` |
| **create_shortcut Desktop not found** | OneDrive Desktop redirect — use latest `create_shortcut.bat`, or open via `run.bat` |
| **pywin32 / Excel print errors** | Re-run `setup.bat` (it configures pywin32) |
| **Tesseract / OCR errors** (Scan tools) | Install [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) to `C:\Program Files\Tesseract-OCR` |
| **pyzbar DLL error** | Install [Microsoft Visual C++ Redistributable](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist) |
| **Folder not syncing** | Check Google Drive for Desktop is running |

### Extra notes
- Path can include spaces (e.g. `MAIN CODE`) — setup/run scripts handle this.
- Optional AI packages (`rembg`) may fail on some PCs; the dashboard still works without them (BG Changer / BW Converter only).
