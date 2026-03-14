

import smtplib
import imaplib
import email
import threading
import time
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import decode_header

try:
    from plyer import notification as plyer_notify
    PLYER_AVAILABLE = True
except ImportError:
    PLYER_AVAILABLE = False


# ─────────────────────────────────────────────
# SMTP – Send Email
# ─────────────────────────────────────────────

def send_email(sender_email: str, password: str, recipient_email: str,
               subject: str, body: str,
               smtp_host: str = "smtp.gmail.com", smtp_port: int = 587) -> bool:
   
    try:
        # Build a MIME message
        msg = MIMEMultipart()
        msg["From"]    = sender_email
        msg["To"]      = recipient_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        # Establish TCP connection → upgrade to TLS → authenticate → send
        print(f"[SMTP] Connecting to {smtp_host}:{smtp_port} …")
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()                        # identify ourselves
            server.starttls()                    # upgrade to TLS
            server.ehlo()                        # re-identify over TLS
            server.login(sender_email, password) # authenticate
            server.sendmail(sender_email, recipient_email, msg.as_string())
            print("[SMTP] Email sent successfully.")
        return True

    except smtplib.SMTPAuthenticationError:
        print("[SMTP] Authentication failed – check credentials / app-password.")
    except smtplib.SMTPConnectError as e:
        print(f"[SMTP] Could not connect to server: {e}")
    except smtplib.SMTPException as e:
        print(f"[SMTP] SMTP error: {e}")
    except Exception as e:
        print(f"[SMTP] Unexpected error: {e}")
    return False


# ─────────────────────────────────────────────
# IMAP – Fetch Latest Email
# ─────────────────────────────────────────────

def fetch_latest_email(email_address: str, password: str,
                       imap_host: str = "imap.gmail.com") -> dict | None:
    """
    Connect to an IMAP server and retrieve the most recent email from INBOX.

    Parameters
    ----------
    email_address : Account email address
    password      : Account password / app-password
    imap_host     : IMAP server hostname (default: Gmail)

    Returns a dict with keys {subject, sender, body} or None on failure.
    """
    try:
        print(f"[IMAP] Connecting to {imap_host} …")
        # Establish TLS-wrapped TCP connection
        mail = imaplib.IMAP4_SSL(imap_host)
        mail.login(email_address, password)
        mail.select("inbox")                     # open the INBOX mailbox

        # Search for ALL messages and take the last UID
        status, messages = mail.search(None, "ALL")
        if status != "OK" or not messages[0]:
            print("[IMAP] Inbox is empty.")
            mail.logout()
            return None

        latest_id = messages[0].split()[-1]
        status, msg_data = mail.fetch(latest_id, "(RFC822)")

        if status != "OK":
            print("[IMAP] Failed to fetch message.")
            mail.logout()
            return None

        raw_email = msg_data[0][1]
        parsed    = email.message_from_bytes(raw_email)

        # Decode subject
        subject_parts = decode_header(parsed["Subject"] or "")
        subject = "".join(
            part.decode(enc or "utf-8") if isinstance(part, bytes) else part
            for part, enc in subject_parts
        )

        sender = parsed.get("From", "Unknown")

        # Extract plain-text body
        body = ""
        if parsed.is_multipart():
            for part in parsed.walk():
                if part.get_content_type() == "text/plain":
                    charset = part.get_content_charset() or "utf-8"
                    body = part.get_payload(decode=True).decode(charset, errors="replace")
                    break
        else:
            charset = parsed.get_content_charset() or "utf-8"
            body = parsed.get_payload(decode=True).decode(charset, errors="replace")

        mail.logout()
        print("[IMAP] Latest email fetched successfully.")
        return {"subject": subject, "sender": sender, "body": body}

    except imaplib.IMAP4.error as e:
        print(f"[IMAP] IMAP error: {e}")
    except ConnectionRefusedError:
        print("[IMAP] Connection refused – verify host/port.")
    except Exception as e:
        print(f"[IMAP] Unexpected error: {e}")
    return None


# ─────────────────────────────────────────────
# Push Notification Helper
# ─────────────────────────────────────────────

def push_notification(title: str, message: str) -> None:
    """
    Show a desktop push notification using Plyer (if available),
    otherwise fall back to a Tkinter messagebox.
    """
    if PLYER_AVAILABLE:
        plyer_notify.notify(
            title=title,
            message=message[:256],   # keep it short
            app_name="Email Client",
            timeout=8,
        )
    else:
        # Non-blocking fallback so we don't freeze the GUI thread
        def _show():
            messagebox.showinfo(title, message)
        threading.Thread(target=_show, daemon=True).start()


# ─────────────────────────────────────────────
# Background Polling Thread
# ─────────────────────────────────────────────

class EmailPoller(threading.Thread):
    """
    Polls the IMAP inbox every `interval` seconds and fires a push
    notification when a new email arrives.
    """

    def __init__(self, email_addr: str, password: str,
                 imap_host: str, interval: int = 60):
        super().__init__(daemon=True)
        self.email_addr = email_addr
        self.password   = password
        self.imap_host  = imap_host
        self.interval   = interval
        self._stop_evt  = threading.Event()
        self._last_uid  = None

    def run(self):
        while not self._stop_evt.is_set():
            try:
                mail = imaplib.IMAP4_SSL(self.imap_host)
                mail.login(self.email_addr, self.password)
                mail.select("inbox")
                _, messages = mail.search(None, "ALL")
                if messages[0]:
                    latest_uid = messages[0].split()[-1]
                    if self._last_uid is None:
                        self._last_uid = latest_uid   # baseline on first run
                    elif latest_uid != self._last_uid:
                        self._last_uid = latest_uid
                        _, msg_data = mail.fetch(latest_uid, "(RFC822)")
                        parsed  = email.message_from_bytes(msg_data[0][1])
                        subject = parsed.get("Subject", "(no subject)")
                        sender  = parsed.get("From", "Unknown")
                        push_notification(
                            "📬 New Email",
                            f"From: {sender}\nSubject: {subject}"
                        )
                mail.logout()
            except Exception as e:
                print(f"[Poller] Error: {e}")
            self._stop_evt.wait(self.interval)

    def stop(self):
        self._stop_evt.set()


class EmailClientApp(tk.Tk):
    """Main Tkinter GUI window."""

    def __init__(self):
        super().__init__()
        self.title("📧 Email Client")
        self.resizable(True, True)
        self.configure(bg="#1e1e2e")
        self._poller: EmailPoller | None = None
        self._build_ui()

    # ── UI construction ──────────────────────

    def _build_ui(self):
        DARK   = "#1e1e2e"
        PANEL  = "#2a2a3d"
        ACCENT = "#7c6af7"
        FG     = "#cdd6f4"
        ENTRY  = "#313244"

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TNotebook",        background=DARK,  borderwidth=0)
        style.configure("TNotebook.Tab",    background=PANEL, foreground=FG,
                        padding=[12, 6],    font=("Segoe UI", 10, "bold"))
        style.map("TNotebook.Tab",          background=[("selected", ACCENT)])
        style.configure("TFrame",           background=DARK)
        style.configure("TLabel",           background=DARK,  foreground=FG,
                        font=("Segoe UI", 10))
        style.configure("TEntry",           fieldbackground=ENTRY, foreground=FG,
                        insertcolor=FG,     font=("Segoe UI", 10))
        style.configure("Accent.TButton",   background=ACCENT, foreground="#fff",
                        font=("Segoe UI", 10, "bold"), padding=8)
        style.map("Accent.TButton",         background=[("active", "#6a5af0")])

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=12, pady=12)

        self._build_send_tab(nb, DARK, FG, ENTRY, ACCENT)
        self._build_receive_tab(nb, DARK, FG, ENTRY, ACCENT)
        self._build_settings_tab(nb, DARK, FG, ENTRY, ACCENT)

    def _label_entry(self, parent, text, show=""):
        ttk.Label(parent, text=text).pack(anchor="w", pady=(8, 2))
        var = tk.StringVar()
        e   = ttk.Entry(parent, textvariable=var, show=show, width=55)
        e.pack(fill="x")
        return var

    def _build_send_tab(self, nb, bg, fg, entry_bg, accent):
        frame = ttk.Frame(nb, padding=16)
        nb.add(frame, text=" ✉  Send ")

        self.send_email_var    = self._label_entry(frame, "Your Email:")
        self.send_password_var = self._label_entry(frame, "Password:", show="●")
        self.send_to_var       = self._label_entry(frame, "Recipient Email:")
        self.send_subject_var  = self._label_entry(frame, "Subject:")

        ttk.Label(frame, text="Body:").pack(anchor="w", pady=(8, 2))
        self.send_body = scrolledtext.ScrolledText(
            frame, height=8, wrap="word",
            bg="#313244", fg=fg, insertbackground=fg,
            font=("Segoe UI", 10), relief="flat"
        )
        self.send_body.pack(fill="both", expand=True)

        ttk.Label(frame, text="SMTP Host:").pack(anchor="w", pady=(8, 2))
        self.smtp_host_var = tk.StringVar(value="smtp.gmail.com")
        ttk.Entry(frame, textvariable=self.smtp_host_var).pack(fill="x")

        ttk.Button(frame, text="Send Email ➤",
                   style="Accent.TButton",
                   command=self._on_send).pack(pady=14)

        self.send_status = ttk.Label(frame, text="")
        self.send_status.pack()

    def _build_receive_tab(self, nb, bg, fg, entry_bg, accent):
        frame = ttk.Frame(nb, padding=16)
        nb.add(frame, text=" 📥  Receive ")

        self.recv_email_var    = self._label_entry(frame, "Your Email:")
        self.recv_password_var = self._label_entry(frame, "Password:", show="●")

        ttk.Label(frame, text="IMAP Host:").pack(anchor="w", pady=(8, 2))
        self.imap_host_var = tk.StringVar(value="imap.gmail.com")
        ttk.Entry(frame, textvariable=self.imap_host_var).pack(fill="x")

        btn_row = ttk.Frame(frame)
        btn_row.pack(fill="x", pady=10)
        ttk.Button(btn_row, text="Fetch Latest Email",
                   style="Accent.TButton",
                   command=self._on_fetch).pack(side="left", padx=(0, 8))
        self.poll_btn = ttk.Button(btn_row, text="▶ Start Polling",
                                   style="Accent.TButton",
                                   command=self._toggle_polling)
        self.poll_btn.pack(side="left")

        ttk.Label(frame, text="Latest Email:").pack(anchor="w")
        self.recv_box = scrolledtext.ScrolledText(
            frame, height=14, wrap="word",
            bg="#313244", fg=fg, insertbackground=fg,
            font=("Segoe UI", 10), relief="flat", state="disabled"
        )
        self.recv_box.pack(fill="both", expand=True)

    def _build_settings_tab(self, nb, bg, fg, entry_bg, accent):
        frame = ttk.Frame(nb, padding=16)
        nb.add(frame, text=" ⚙  Settings ")

        ttk.Label(frame,
                  text="Poll interval (seconds):").pack(anchor="w", pady=(8, 2))
        self.poll_interval_var = tk.IntVar(value=60)
        ttk.Spinbox(frame, from_=10, to=3600,
                    textvariable=self.poll_interval_var, width=10).pack(anchor="w")

        ttk.Label(frame,
                  text="Plyer notifications available: "
                  + ("✅ Yes" if PLYER_AVAILABLE else "❌ No (pip install plyer)"),
                  foreground="#a6e3a1" if PLYER_AVAILABLE else "#f38ba8"
                  ).pack(anchor="w", pady=12)

        ttk.Label(frame,
                  text="Tips:\n"
                  "• Gmail users: enable 2FA and use an App Password.\n"
                  "• For mail.tm, use the API to create a disposable address.\n"
                  "• SMTP port 587 (STARTTLS) is the default.",
                  justify="left").pack(anchor="w", pady=8)

    # ── Action handlers ──────────────────────

    def _on_send(self):
        e = self.send_email_var.get().strip()
        p = self.send_password_var.get()
        t = self.send_to_var.get().strip()
        s = self.send_subject_var.get().strip()
        b = self.send_body.get("1.0", "end").strip()
        h = self.smtp_host_var.get().strip()

        if not all([e, p, t, s, b]):
            messagebox.showwarning("Missing Fields", "Please fill in all fields.")
            return

        self.send_status.config(text="Sending…", foreground="#fab387")
        self.update_idletasks()

        def _run():
            ok = send_email(e, p, t, s, b, smtp_host=h)
            self.after(0, lambda: self.send_status.config(
                text="✅ Sent successfully!" if ok else "❌ Failed – see console.",
                foreground="#a6e3a1" if ok else "#f38ba8"
            ))

        threading.Thread(target=_run, daemon=True).start()

    def _on_fetch(self):
        e = self.recv_email_var.get().strip()
        p = self.recv_password_var.get()
        h = self.imap_host_var.get().strip()

        if not all([e, p]):
            messagebox.showwarning("Missing Fields",
                                   "Please enter your email and password.")
            return

        def _run():
            result = fetch_latest_email(e, p, imap_host=h)
            self.after(0, lambda: self._display_email(result))

        threading.Thread(target=_run, daemon=True).start()

    def _display_email(self, result: dict | None):
        self.recv_box.config(state="normal")
        self.recv_box.delete("1.0", "end")
        if result:
            self.recv_box.insert("end",
                f"From:    {result['sender']}\n"
                f"Subject: {result['subject']}\n"
                f"{'─' * 60}\n\n"
                f"{result['body']}"
            )
        else:
            self.recv_box.insert("end", "No email found or an error occurred.")
        self.recv_box.config(state="disabled")

    def _toggle_polling(self):
        if self._poller and self._poller.is_alive():
            # Stop
            self._poller.stop()
            self._poller = None
            self.poll_btn.config(text="▶ Start Polling")
        else:
            # Start
            e = self.recv_email_var.get().strip()
            p = self.recv_password_var.get()
            h = self.imap_host_var.get().strip()
            if not all([e, p]):
                messagebox.showwarning("Missing Fields",
                                       "Enter email and password first.")
                return
            interval = self.poll_interval_var.get()
            self._poller = EmailPoller(e, p, h, interval=interval)
            self._poller.start()
            self.poll_btn.config(text="⏹ Stop Polling")
            messagebox.showinfo("Polling Started",
                                f"Checking inbox every {interval}s.\n"
                                "You'll get a desktop notification on new mail.")

    def destroy(self):
        if self._poller:
            self._poller.stop()
        super().destroy()


# ─────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    app = EmailClientApp()
    app.mainloop()