# SafeNest

SafeNest is a comprehensive, real-time safety and security platform built with Flask and WebSockets. It acts as a centralized dashboard and tactical hub for monitoring incidents, dispatching emergency responses (SOS), and maintaining community safety through data-driven insights.

## 🚀 Features



### Core Capabilities
* **SOS & Emergency Alerts:** One-click SOS capability that instantly alerts administrators with the user's real-time location.
* **Safety Map (Tactical View):** An interactive map displaying active incident hotspots, safe corridors, and real-time user proximity alerts.
* **Whistleblower Portal:** A secure, anonymous reporting mechanism for users to submit sensitive information, complete with a 2-way anonymous chat for follow-ups.
* **Guardian Pulse:** A periodic "check-in" system to proactively monitor user safety in high-risk scenarios.
* **AI Triage System:** Automated heuristic-based parsing of incident descriptions to categorize and prioritize them, generating actionable response instructions.

### Admin Dashboard
* Real-time tracking of all active alerts via WebSockets.
* Ability to broadcast critical alerts to all users.
* Incident analytics (e.g., Justice Analytics) and Hotspot generation.

## 🏗 Technology Stack

* **Backend:** Python, Flask, Flask-SocketIO
* **Database:** SQLite (`safenest.db`)
* **Frontend:** HTML, CSS, JavaScript (Vanilla), Socket.IO client
* **Concurrency:** Eventlet & threading for real-time and background tasks

## 🛠 Setup & Installation

Follow these steps to run SafeNest locally.

### Prerequisites

* Python 3.8+
* [Git](https://git-scm.com/)

### 1. Clone the repository

```bash
git clone https://github.com/ajinkyachalke008/SafeNest-.git
cd SafeNest-
```

### 2. Set up a virtual environment (Recommended)

```bash
python -m venv venv
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Initialize the Database

Use the setup script to create tables and generate seed data:

```bash
python init_db.py
```
*(Also, you can run `python seed_tactical.py` to pre-populate dummy emergency data for testing)*

### 5. Run the Application

Start the Flask-SocketIO server using Eventlet:

```bash
python app.py
```
*(Make sure to use `python app.py` or `flask run` depending on your environment. Note that since WebSockets require Eventlet, running the file directly via `python app.py` is often best to ensure `socketio.run()` is used).*

The application will be accessible at `http://127.0.0.1:5000/`.

## 🔒 Security Notes

* Currently, the app uses simple HTTP and session-based authentication. 
* To deploy in a real-world scenario (Production), ensure the app is served over **HTTPS** (wss:// for WebSockets) so location data and credentials are encrypted in transit.

## 🤝 Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

## 📄 License

[MIT](https://choosealicense.com/licenses/mit/)
