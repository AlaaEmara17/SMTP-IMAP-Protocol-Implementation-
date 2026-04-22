# Email Client

A Python-based email client with GUI for sending and receiving emails via SMTP and IMAP protocols. Features secure TLS connections, real-time notifications, and background polling.

## Features

- **Email Operations**: Send emails via SMTP and fetch latest emails via IMAP
- **Security**: TLS encryption for all connections
- **Notifications**: Desktop notifications for new emails (with plyer) or fallback message boxes
- **Background Polling**: Configurable inbox monitoring
- **GUI**: Modern dark-themed Tkinter interface with tabbed layout
- **Threading**: Non-blocking operations for responsive UI

## Requirements

- Python 3.8+
- `plyer` (optional, for desktop notifications)

## Installation

```bash
git clone https://github.com/AlaaEmara17/Network_Lab2.git
cd Network_Lab2
pip install plyer  # Optional
python gui.py
```

## Usage

### Sending Emails
1. Enter sender credentials and SMTP host (default: smtp.gmail.com)
2. Fill recipient, subject, and body
3. Click "Send Email"

### Receiving Emails
1. Enter credentials and IMAP host (default: imap.gmail.com)
2. Click "Fetch Latest Email" or "Start Polling" for continuous monitoring

### Gmail Setup
Enable 2FA and use App Password instead of regular password.

## Project Structure

- `email_functions.py`: Email operations, notifications, and polling
- `gui.py`: Tkinter GUI implementation
- `email_client.py`: Legacy entry point

## Architecture

Modular design with separation of email logic and GUI. Uses threading for network operations to maintain UI responsiveness.

## Security

- TLS encryption for SMTP/IMAP
- Credentials stored in memory only
- App passwords recommended for Gmail

## Troubleshooting

- **Authentication errors**: Verify credentials and app passwords
- **Connection issues**: Check network and firewall settings
- **No notifications**: Install plyer or use message box fallback
- Debug logs available in console


## Author

Alaa Emara - [GitHub](https://github.com/AlaaEmara17/Network_Lab2)</content>
<parameter name="filePath">c:\Users\alaae\OneDrive\Desktop\Network_Lab2\README.md