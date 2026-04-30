import os
import subprocess
import shutil
from tkinter import messagebox


def download_sample(svc):
    """Copy the sample file to the user's Desktop and open it in Explorer."""
    sample_path = svc.get("sample")
    if not sample_path:
        messagebox.showinfo(
            "No Sample",
            f"No sample file is available for '{svc['title']}' yet."
        )
        return
    if not os.path.exists(sample_path):
        messagebox.showwarning(
            "Sample Not Found",
            f"The sample file for '{svc['title']}' has not been added yet.\n\n"
            f"Expected location:\n{sample_path}"
        )
        return
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    dest    = os.path.join(desktop, os.path.basename(sample_path))
    try:
        shutil.copy2(sample_path, dest)
        subprocess.Popen(["explorer", "/select,", dest])
        messagebox.showinfo(
            "Sample Downloaded",
            f"Sample file saved to your Desktop:\n{os.path.basename(sample_path)}"
        )
    except Exception as e:
        messagebox.showerror("Error", f"Could not copy sample file:\n{e}")
