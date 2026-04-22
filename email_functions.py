import smtplib
import imaplib
import email
import threading
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import decode_header

try:
    from plyer import notification as plyer_notify
    PLYER_AVAILABLE = True
except ImportError:
    PLYER_AVAILABLE = False


def send_email(sender_email: str, password: str, recipient_email: str,
               subject: str, body: str,
               smtp_host: str = "smtp.gmail.com", smtp_port: int = 587) -> bool:
    """
    Sends an email using SMTP with TLS encryption.

    Args:
        sender_email (str): The sender's email address.
        password (str): The sender's password or app password.
        recipient_email (str): The recipient's email address.
        subject (str): The email subject.
        body (str): The email body text.
        smtp_host (str): SMTP server host (default: smtp.gmail.com).
        smtp_port (int): SMTP server port (default: 587).

    Returns:
        bool: True if email sent successfully, False otherwise.
    """
    try:
        # Build a MIME message
        msg = MIMEMultipart()
        msg["From"]    = sender_email
        msg["To"]      = recipient_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        #TLS is encrypted but still uses the same SMTP port (587) and workflow:
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


def fetch_latest_email(email_address: str, password: str,
                       imap_host: str = "imap.gmail.com") -> dict | None:
    """
    Fetches the latest email from the inbox using IMAP.

    Args:
        email_address (str): The email address to fetch from.
        password (str): The password or app password.
        imap_host (str): IMAP server host (default: imap.gmail.com).

    Returns:
        dict | None: Dictionary with 'subject', 'sender', 'body' if successful, None otherwise.
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


def push_notification(title: str, message: str) -> None:
    """
    Shows a push notification or fallback message box.

    Args:
        title (str): Notification title.
        message (str): Notification message.
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
        import tkinter as tk
        from tkinter import messagebox
        def _show():
            messagebox.showinfo(title, message)
        threading.Thread(target=_show, daemon=True).start()


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
