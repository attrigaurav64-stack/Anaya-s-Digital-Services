# CyberCafePro - Cyber Cafe Query Management System

## Install
1. Install Python 3 and PostgreSQL.
2. Create database in PostgreSQL:

```sql
CREATE DATABASE cybercafe_db;
```

3. Open this folder in VS Code.
4. Create `.env` file by copying `.env.example` and change your PostgreSQL password and WhatsApp number.
5. Install packages:

```bash
pip install -r requirements.txt
```

6. Run:

```bash
python app.py
```

7. Open:

```text
http://127.0.0.1:5000
```

Default login:

```text
Username: admin
Password: admin123
```

## Important
This version creates QR code and saves queries from dashboard manually. Automatic WhatsApp message saving needs WhatsApp Cloud API webhook setup later.
