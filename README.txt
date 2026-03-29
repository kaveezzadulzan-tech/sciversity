# Sciversity – Attendance & Finance Portal
## Setup Guide (Windows with Antigravity / Python installed)

---

## STEP 1 — Install Python
If not already installed:
👉 https://www.python.org/downloads/
- During install: CHECK ✅ "Add Python to PATH"
- After install, open CMD and type: python --version

---

## STEP 2 — Copy the project folder
Put the `sciversity` folder anywhere, e.g.:
  C:\Users\YourName\Desktop\sciversity\

---

## STEP 3 — Open Command Prompt in the folder
- Open File Explorer → navigate into the `sciversity` folder
- Click the address bar, type `cmd`, press Enter

---

## STEP 4 — Install dependencies
In the CMD window, paste this and press Enter:
  pip install -r requirements.txt

Wait for it to finish (takes ~1 minute).

---

## STEP 5 — Run the app
In the same CMD window:
  python app.py

You'll see:
  ✅ Default admin created: admin / sciversity2024
  * Running on http://0.0.0.0:5000

---

## STEP 6 — Open in your browser
Go to: http://localhost:5000

Login as admin:
  Username: admin
  Password: sciversity2024

---

## HOW TO USE

### Adding Students
1. Admin Dashboard → "Add New Student" panel
2. Enter name, email, and a password for them
3. Click "Add Student"
4. Click the QR icon on their row → Print their card

### Scanning QR Codes
1. On Admin Dashboard → pick Session Duration (e.g. 2h)
2. Click "Start Camera Scanner"
3. Allow camera access
4. Scan the student's QR card → system logs hours automatically

### Marking Payment
- When a student hits 8 hours, their row turns RED
- Click the ✓ (green checkmark) button on their row
- This resets their meter for the next 8-hour block

### Posting Homework
1. Admin Dashboard → "Post Homework" panel
2. Type the task title + optional description
3. Click "Broadcast" → all students see it immediately

### Student Login
- Students go to: http://YOUR-COMPUTER-IP:5000/student/login
- They use the email + password you set for them
- They can see their hour meter, homework, and attendance log

### Finding your IP (to share with students on same WiFi)
- Open CMD and type: ipconfig
- Look for "IPv4 Address" under your WiFi adapter
- Students on the same WiFi use: http://192.168.X.X:5000/student/login

---

## FILES EXPLAINED
- app.py          → Main application (Flask backend)
- requirements.txt → Python packages needed
- templates/       → HTML pages
- sciversity.db    → Database (created automatically on first run)

---

## DEFAULT ADMIN CREDENTIALS
Username: admin
Password: sciversity2024
⚠️ Change this in app.py → init_db() before going live!
