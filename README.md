# Dashboard - Setup Guide

## How it works
This folder lives in a shared Google Drive and syncs automatically.
When new tools are added, they appear on your device without any action from you.

---

## First time on a new device — 3 steps

### Step 1 — Install Python (once ever)
Download and install Python from:
**https://www.python.org/downloads/**

> ⚠️ During installation, tick **"Add Python to PATH"**

---

### Step 2 — Install Google Drive for Desktop (once ever)
Download from: **https://drive.google.com/drive/download**

Sign in with the Google account this folder was shared with.
The DASHBOARD folder will appear on your computer automatically — no manual downloading.

---

### Step 3 — Run setup (once per device)
Inside the DASHBOARD folder, double-click **`setup.bat`**

This installs all required libraries. Takes about a minute.
You only ever need to do this once per device.

---

### Step 4 — Create a Desktop shortcut (once per device)
Inside the DASHBOARD folder, double-click **`create_shortcut.bat`**

This places a **Dashboard** shortcut on your Desktop.
You never need to open Google Drive again.

---

## Opening the dashboard (every day)
Double-click the **Dashboard** shortcut on your Desktop.

That's it. The dashboard always opens the latest version automatically.

---

## Getting updates
Nothing to do. When new tools or changes are made, Google Drive syncs them
to your device in the background. Just open `run.bat` as usual.

The only exception: if a new tool uses a new library, you'll see a message
asking you to run `setup.bat` once more. This will be rare.

---

## Folder structure
```
DASHBOARD/
├── dashboard.py        ← Main app (do not move or rename)
├── run.bat             ← Open the dashboard — double-click this daily
├── setup.bat           ← First-time setup — run once per device
├── requirements.txt    ← Library list (do not edit)
├── scripts/            ← All tool scripts (auto-synced)
└── samples/            ← Sample files for each tool (auto-synced)
```

---

## Trouble?
- **"Python not found"** → Re-install Python and tick "Add Python to PATH"
- **"Module not found"** → Run `setup.bat` again
- **Folder not syncing** → Check Google Drive for Desktop is running (look for the Drive icon in your taskbar)
