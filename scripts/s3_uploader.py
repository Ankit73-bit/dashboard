import customtkinter as ctk
from tkinter import filedialog, messagebox
import threading
import os
import shutil
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
import boto3
from botocore.exceptions import NoCredentialsError, ClientError

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

C = {
    "bg":     "#0a0a0f",
    "card":   "#16161f",
    "border": "#2a2a3d",
    "hover":  "#1e1e2e",
    "text":   "#e8e8f0",
    "muted":  "#8888aa",
    "faint":  "#44445a",
    "accent": "#0a84ff",   # blue
    "green":  "#30d158",
    "red":    "#ff375f",
    "orange": "#ff9f0a",
}
TINT = {"bg": "#001830", "mid": "#002850", "bdr": "#003d78"}

# ─── Load .env from same folder as this script ────────────────────────────────
HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(HERE, "..", ".env")   # DASHBOARD/.env
load_dotenv(ENV_PATH)

AWS_KEY    = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET = os.getenv("AWS_SECRET_ACCESS_KEY", "")
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")
S3_BUCKET  = os.getenv("S3_BUCKET_NAME", "")

# ─── Failed files output dir ──────────────────────────────────────────────────
def get_failed_dir():
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    ts      = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path    = os.path.join(desktop, "OUTPUT", "S3_Upload", ts, "failed")
    os.makedirs(path, exist_ok=True)
    return path

# ─── S3 upload (single file) ──────────────────────────────────────────────────
def upload_one(local_path, s3_key):
    try:
        s3 = boto3.client(
            "s3",
            aws_access_key_id=AWS_KEY,
            aws_secret_access_key=AWS_SECRET,
            region_name=AWS_REGION,
        )
        ext = os.path.splitext(local_path)[1].lower()
        content_type_map = {
            ".pdf":  "application/pdf",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".xls":  "application/vnd.ms-excel",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".doc":  "application/msword",
            ".png":  "image/png",
            ".jpg":  "image/jpeg",
            ".jpeg": "image/jpeg",
            ".csv":  "text/csv",
            ".txt":  "text/plain",
        }
        content_type = content_type_map.get(ext, "application/octet-stream")
        s3.upload_file(
            local_path, S3_BUCKET, s3_key,
            ExtraArgs={"ContentType": content_type, "ContentDisposition": "inline"}
        )
        return (local_path, True, None)
    except FileNotFoundError:
        return (local_path, False, "File not found")
    except NoCredentialsError:
        return (local_path, False, "Invalid AWS credentials")
    except ClientError as e:
        return (local_path, False, str(e))
    except Exception as e:
        return (local_path, False, str(e))


# ─── App ──────────────────────────────────────────────────────────────────────
class S3UploaderApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("S3 File Uploader")
        self.geometry("780x900")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])

        # State
        self.all_files   = []   # full list of resolved file paths
        self.ext_vars    = {}   # ext → BooleanVar (filter checkboxes)
        self.source_items = []  # display items (files/folders added by user)

        self._build()

    # ─── Build UI ─────────────────────────────────────────────────────────────
    def _build(self):
        # Header
        hdr = ctk.CTkFrame(self, fg_color=TINT["bg"], corner_radius=0)
        hdr.pack(fill="x")
        inner = ctk.CTkFrame(hdr, fg_color="transparent")
        inner.pack(padx=28, pady=16)

        icon_f = ctk.CTkFrame(inner, width=48, height=48,
                              fg_color=TINT["mid"], corner_radius=12)
        icon_f.pack(side="left", padx=(0, 14))
        icon_f.pack_propagate(False)
        ctk.CTkLabel(icon_f, text="☁️",
                     font=ctk.CTkFont("Segoe UI Emoji", 22)
                     ).place(relx=0.5, rely=0.5, anchor="center")

        txt = ctk.CTkFrame(inner, fg_color="transparent")
        txt.pack(side="left")
        ctk.CTkLabel(txt, text="S3 File Uploader",
                     font=ctk.CTkFont("Segoe UI", 18, "bold"),
                     text_color=C["text"]).pack(anchor="w")
        ctk.CTkLabel(txt, text="Upload files or folders to Amazon S3 in parallel",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"]).pack(anchor="w")

        # Credentials status badge
        creds_ok = all([AWS_KEY, AWS_SECRET, S3_BUCKET])
        badge_color = C["green"] if creds_ok else C["red"]
        badge_text  = f"✓  Connected · {S3_BUCKET}" if creds_ok else "✗  Credentials missing in .env"
        ctk.CTkLabel(inner, text=badge_text,
                     font=ctk.CTkFont("Segoe UI", 10, "bold"),
                     text_color=badge_color
                     ).pack(side="right", padx=(20, 0))

        # Scrollable body
        body = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                      scrollbar_button_color=C["border"])
        body.pack(fill="both", expand=True, padx=24, pady=16)

        # ── Step 1: Add files / folders ──
        self._section(body, "Step 1 — Add files or folders")

        btn_row = ctk.CTkFrame(body, fg_color="transparent")
        btn_row.pack(fill="x", pady=(4, 6))

        ctk.CTkButton(btn_row, text="＋ Add Files",
                      font=ctk.CTkFont("Segoe UI", 12, "bold"),
                      fg_color=TINT["mid"], hover_color=TINT["bdr"],
                      text_color=C["accent"], border_color=C["accent"], border_width=1,
                      corner_radius=20, height=36, width=140,
                      command=self._add_files
                      ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(btn_row, text="＋ Add Folders",
                      font=ctk.CTkFont("Segoe UI", 12, "bold"),
                      fg_color=TINT["mid"], hover_color=TINT["bdr"],
                      text_color=C["accent"], border_color=C["accent"], border_width=1,
                      corner_radius=20, height=36, width=140,
                      command=self._add_folders
                      ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(btn_row, text="Clear All",
                      font=ctk.CTkFont("Segoe UI", 12),
                      fg_color="transparent", hover_color=C["hover"],
                      text_color=C["muted"],
                      corner_radius=20, height=36, width=90,
                      command=self._clear_all
                      ).pack(side="right")

        # Source list card
        self.source_card = ctk.CTkFrame(body, fg_color=C["card"], corner_radius=12,
                                        border_width=1, border_color=C["border"])
        self.source_card.pack(fill="x", pady=(0, 10))

        self.source_placeholder = ctk.CTkLabel(
            self.source_card,
            text="No files or folders added yet",
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=C["faint"])
        self.source_placeholder.pack(padx=16, pady=16)

        # File count summary
        self.summary_label = ctk.CTkLabel(
            body, text="",
            font=ctk.CTkFont("Segoe UI", 11, "bold"),
            text_color=C["muted"], anchor="w")
        self.summary_label.pack(fill="x", pady=(0, 4))

        # ── Step 2: File type filter (dynamic) ──
        self._section(body, "Step 2 — Filter by file type")

        self.filter_card = ctk.CTkFrame(body, fg_color=C["card"], corner_radius=12,
                                        border_width=1, border_color=C["border"])
        self.filter_card.pack(fill="x", pady=(4, 10))

        self.filter_placeholder = ctk.CTkLabel(
            self.filter_card,
            text="File types will appear here once you add files",
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=C["faint"])
        self.filter_placeholder.pack(padx=16, pady=14)

        # ── Step 3: S3 upload path ──
        self._section(body, "Step 3 — S3 upload path (folder inside bucket)")

        path_card = ctk.CTkFrame(body, fg_color=C["card"], corner_radius=12,
                                 border_width=1, border_color=C["border"])
        path_card.pack(fill="x", pady=(4, 10))

        path_inner = ctk.CTkFrame(path_card, fg_color="transparent")
        path_inner.pack(fill="x", padx=16, pady=12)

        ctk.CTkLabel(path_inner,
                     text=f"{S3_BUCKET}/",
                     font=ctk.CTkFont("Courier New", 12),
                     text_color=C["muted"]).pack(side="left")

        self.s3_path = ctk.CTkEntry(
            path_inner,
            placeholder_text="uploads/documents/2024",
            font=ctk.CTkFont("Courier New", 12),
            fg_color=C["hover"], border_color=C["border"],
            text_color=C["text"], height=34)
        self.s3_path.pack(side="left", fill="x", expand=True, padx=(4, 0))

        ctk.CTkLabel(path_card,
                     text="  Files will be uploaded to: s3://<bucket>/<path>/<filename>",
                     font=ctk.CTkFont("Segoe UI", 10),
                     text_color=C["faint"], anchor="w"
                     ).pack(fill="x", padx=16, pady=(0, 10))

        # ── Progress & log ──
        self._section(body, "Progress")

        self.progress = ctk.CTkProgressBar(body, height=8,
                                           fg_color=C["card"],
                                           progress_color=C["accent"])
        self.progress.pack(fill="x", pady=(4, 8))
        self.progress.set(0)

        # Stats row
        stats_row = ctk.CTkFrame(body, fg_color="transparent")
        stats_row.pack(fill="x", pady=(0, 8))

        self.stat_total   = self._stat_badge(stats_row, "Total",   "0", C["accent"])
        self.stat_success = self._stat_badge(stats_row, "Uploaded", "0", C["green"])
        self.stat_failed  = self._stat_badge(stats_row, "Failed",   "0", C["red"])
        self.stat_skipped = self._stat_badge(stats_row, "Skipped",  "0", C["orange"])

        self.log = ctk.CTkTextbox(body, height=150,
                                  font=ctk.CTkFont("Courier New", 11),
                                  fg_color=C["card"],
                                  border_color=C["border"], border_width=1,
                                  text_color=C["muted"],
                                  state="disabled")
        self.log.pack(fill="x", pady=(0, 16))

        # ── Upload button ──
        self.run_btn = ctk.CTkButton(
            body, text="☁️  Upload to S3",
            font=ctk.CTkFont("Segoe UI", 14, "bold"),
            fg_color=TINT["mid"], hover_color=TINT["bdr"],
            text_color=C["accent"],
            border_color=C["accent"], border_width=1,
            corner_radius=24, height=48,
            command=self._start)
        self.run_btn.pack(fill="x", pady=(0, 20))

    # ─── UI helpers ───────────────────────────────────────────────────────────
    def _section(self, parent, text):
        ctk.CTkLabel(parent, text=text,
                     font=ctk.CTkFont("Segoe UI", 12, "bold"),
                     text_color=C["text"], anchor="w"
                     ).pack(fill="x", pady=(14, 2))

    def _stat_badge(self, parent, label, val, color):
        f = ctk.CTkFrame(parent, fg_color=C["card"], corner_radius=10,
                         border_width=1, border_color=C["border"])
        f.pack(side="left", padx=(0, 8))
        v_lbl = ctk.CTkLabel(f, text=val,
                             font=ctk.CTkFont("Segoe UI", 18, "bold"),
                             text_color=color)
        v_lbl.pack(padx=14, pady=(6, 0))
        ctk.CTkLabel(f, text=label,
                     font=ctk.CTkFont("Segoe UI", 10),
                     text_color=C["muted"]).pack(padx=14, pady=(0, 6))
        return v_lbl

    def _log(self, msg):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    # ─── Add files / folders ──────────────────────────────────────────────────
    def _add_files(self):
        paths = filedialog.askopenfilenames(title="Select files to upload")
        if paths:
            for p in paths:
                if p not in self.source_items:
                    self.source_items.append(p)
            self._refresh_sources()

    def _add_folders(self):
        folder = filedialog.askdirectory(title="Select folder to upload")
        if folder and folder not in self.source_items:
            self.source_items.append(folder)
            self._refresh_sources()

    def _clear_all(self):
        self.source_items.clear()
        self.all_files.clear()
        self._refresh_sources()

    def _remove_item(self, item):
        if item in self.source_items:
            self.source_items.remove(item)
        self._refresh_sources()

    # ─── Resolve all files from sources ──────────────────────────────────────
    def _resolve_files(self):
        """Walk all source items and resolve to individual file paths."""
        files = []
        for item in self.source_items:
            if os.path.isfile(item):
                files.append(item)
            elif os.path.isdir(item):
                for root, _, filenames in os.walk(item):
                    for fname in filenames:
                        files.append(os.path.join(root, fname))
        # Deduplicate preserving order
        seen = set()
        result = []
        for f in files:
            if f not in seen:
                seen.add(f)
                result.append(f)
        return result

    # ─── Refresh source list display ──────────────────────────────────────────
    def _refresh_sources(self):
        # Resolve files
        self.all_files = self._resolve_files()

        # Clear source card
        for w in self.source_card.winfo_children():
            w.destroy()

        if not self.source_items:
            self.source_placeholder = ctk.CTkLabel(
                self.source_card,
                text="No files or folders added yet",
                font=ctk.CTkFont("Segoe UI", 11),
                text_color=C["faint"])
            self.source_placeholder.pack(padx=16, pady=16)
            self.summary_label.configure(text="")
            self._refresh_filters([])
            return

        # Show each source item with remove button
        for item in self.source_items:
            row = ctk.CTkFrame(self.source_card, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=3)

            is_dir = os.path.isdir(item)
            icon   = "📁" if is_dir else "📄"
            name   = os.path.basename(item)

            ctk.CTkLabel(row, text=f"  {icon}  {name}",
                         font=ctk.CTkFont("Segoe UI", 11),
                         text_color=C["text"], anchor="w"
                         ).pack(side="left", fill="x", expand=True)

            if is_dir:
                count = sum(1 for _ in self._walk_folder(item))
                ctk.CTkLabel(row, text=f"{count} files",
                             font=ctk.CTkFont("Segoe UI", 10),
                             text_color=C["muted"]
                             ).pack(side="left", padx=(0, 8))

            ctk.CTkButton(row, text="✕",
                          font=ctk.CTkFont("Segoe UI", 11),
                          fg_color="transparent", hover_color=C["hover"],
                          text_color=C["muted"],
                          width=28, height=28, corner_radius=14,
                          command=lambda i=item: self._remove_item(i)
                          ).pack(side="right")

        ctk.CTkFrame(self.source_card, height=6, fg_color="transparent").pack()

        # Summary
        total = len(self.all_files)
        self.summary_label.configure(
            text=f"{total} file{'s' if total != 1 else ''} ready to upload",
            text_color=C["accent"])

        # Refresh filters
        exts = sorted({os.path.splitext(f)[1].lower() for f in self.all_files if os.path.splitext(f)[1]})
        self._refresh_filters(exts)

    def _walk_folder(self, folder):
        for root, _, files in os.walk(folder):
            for f in files:
                yield os.path.join(root, f)

    # ─── Refresh file type filter checkboxes ──────────────────────────────────
    def _refresh_filters(self, exts):
        for w in self.filter_card.winfo_children():
            w.destroy()
        self.ext_vars = {}

        if not exts:
            ctk.CTkLabel(self.filter_card,
                         text="File types will appear here once you add files",
                         font=ctk.CTkFont("Segoe UI", 11),
                         text_color=C["faint"]).pack(padx=16, pady=14)
            return

        if len(exts) == 1:
            ctk.CTkLabel(self.filter_card,
                         text=f"All files are {exts[0]}  —  all will be uploaded",
                         font=ctk.CTkFont("Segoe UI", 11),
                         text_color=C["muted"]).pack(padx=16, pady=14)
            # Still create a var so upload logic works
            var = ctk.BooleanVar(value=True)
            self.ext_vars[exts[0]] = var
            return

        # Multiple extensions — show filter UI
        hdr_row = ctk.CTkFrame(self.filter_card, fg_color="transparent")
        hdr_row.pack(fill="x", padx=14, pady=(10, 4))

        ctk.CTkLabel(hdr_row,
                     text="Multiple file types found — choose which to upload:",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"]).pack(side="left")

        ctk.CTkButton(hdr_row, text="All",
                      font=ctk.CTkFont("Segoe UI", 10),
                      fg_color="transparent", hover_color=C["hover"],
                      text_color=C["accent"], height=24, width=40,
                      command=lambda: self._toggle_exts(True)
                      ).pack(side="right")
        ctk.CTkButton(hdr_row, text="None",
                      font=ctk.CTkFont("Segoe UI", 10),
                      fg_color="transparent", hover_color=C["hover"],
                      text_color=C["muted"], height=24, width=48,
                      command=lambda: self._toggle_exts(False)
                      ).pack(side="right", padx=(0, 4))

        ctk.CTkFrame(self.filter_card, height=1,
                     fg_color=C["border"]).pack(fill="x", padx=14)

        grid = ctk.CTkFrame(self.filter_card, fg_color="transparent")
        grid.pack(fill="x", padx=14, pady=(8, 12))

        for i, ext in enumerate(exts):
            count = sum(1 for f in self.all_files if f.lower().endswith(ext))
            var   = ctk.BooleanVar(value=True)
            self.ext_vars[ext] = var
            ctk.CTkCheckBox(
                grid,
                text=f"{ext}  ({count})",
                variable=var,
                font=ctk.CTkFont("Segoe UI", 11),
                text_color=C["text"],
                fg_color=C["accent"],
                hover_color=TINT["bdr"],
                border_color=C["border"],
                checkmark_color=C["bg"]
            ).grid(row=i // 4, column=i % 4, padx=10, pady=4, sticky="w")

    def _toggle_exts(self, state):
        for var in self.ext_vars.values():
            var.set(state)

    # ─── Upload ───────────────────────────────────────────────────────────────
    def _start(self):
        if not self.all_files:
            messagebox.showwarning("No Files", "Please add at least one file or folder.")
            return

        selected_exts = {ext for ext, var in self.ext_vars.items() if var.get()}
        if not selected_exts:
            messagebox.showwarning("No Types Selected", "Please select at least one file type to upload.")
            return

        s3_path = self.s3_path.get().strip().strip("/")
        if not s3_path:
            messagebox.showwarning("No Path", "Please enter an S3 upload path (folder inside the bucket).")
            return

        if not all([AWS_KEY, AWS_SECRET, S3_BUCKET]):
            messagebox.showerror("Credentials Missing",
                                 "AWS credentials or bucket name are missing.\n"
                                 "Please check the .env file.")
            return

        # Filter files by selected extensions
        files_to_upload = [
            f for f in self.all_files
            if os.path.splitext(f)[1].lower() in selected_exts
        ]
        skipped = len(self.all_files) - len(files_to_upload)

        if not files_to_upload:
            messagebox.showwarning("No Files", "No files match the selected file types.")
            return

        self.run_btn.configure(state="disabled", text="Uploading…")
        self.progress.set(0)
        self.stat_total.configure(text=str(len(files_to_upload)))
        self.stat_success.configure(text="0")
        self.stat_failed.configure(text="0")
        self.stat_skipped.configure(text=str(skipped))

        threading.Thread(
            target=self._run,
            args=(files_to_upload, s3_path, skipped),
            daemon=True
        ).start()

    def _run(self, files, s3_path, skipped):
        total      = len(files)
        success    = 0
        failed     = []
        failed_dir = get_failed_dir()

        self._log(f"Starting upload of {total} file(s) to s3://{S3_BUCKET}/{s3_path}/")
        if skipped:
            self._log(f"Skipping {skipped} file(s) based on type filter\n")

        def do_upload(local_path):
            fname  = os.path.basename(local_path)
            s3_key = f"{s3_path}/{fname}"
            return upload_one(local_path, s3_key)

        done = 0
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {executor.submit(do_upload, f): f for f in files}
            for future in as_completed(futures):
                local_path, ok, err = future.result()
                fname = os.path.basename(local_path)
                done += 1

                if ok:
                    success += 1
                    self._log(f"✅  [{done}/{total}]  {fname}")
                else:
                    failed.append(local_path)
                    self._log(f"❌  [{done}/{total}]  {fname}  →  {err}")
                    # Copy failed file to failed dir
                    try:
                        shutil.copy(local_path, os.path.join(failed_dir, fname))
                    except Exception:
                        pass

                self.progress.set(done / total)
                self.stat_success.configure(text=str(success))
                self.stat_failed.configure(text=str(len(failed)))

        self._log(f"\n{'─' * 44}")
        self._log(f"Done.  {success} uploaded  |  {len(failed)} failed  |  {skipped} skipped")

        if failed:
            self._log(f"Failed files copied to:\n  {failed_dir}")

        self.run_btn.configure(state="normal", text="☁️  Upload to S3")

        if len(failed) == 0:
            messagebox.showinfo("Upload Complete",
                                f"All {success} file(s) uploaded successfully.")
        else:
            messagebox.showwarning("Upload Complete with Errors",
                                   f"{success} uploaded  |  {len(failed)} failed\n\n"
                                   f"Failed files saved to:\n{failed_dir}")


if __name__ == "__main__":
    S3UploaderApp().mainloop()
