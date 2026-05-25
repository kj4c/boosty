import copy
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, jsonify, send_from_directory

import mailing

app = Flask(__name__, static_folder="static")
SESSIONS = {}
SESSION_LOCK = threading.Lock()
WATCH_TIMEOUT_SECONDS = 120

STATIC_DIR = Path(__file__).parent / "static"


def get_session(session_id):
    with SESSION_LOCK:
        session = SESSIONS.get(session_id)
        return copy.deepcopy(session) if session else None


def save_session(session_id, data):
    with SESSION_LOCK:
        SESSIONS[session_id] = data


def stop_watching(session, reason):
    session["watching"] = False
    session["finished"] = True
    session["finish_reason"] = reason
    return session


def watch_expired(session):
    started = session.get("watch_started_at")
    if not started or not session.get("watching"):
        return False
    return (time.time() - started) >= WATCH_TIMEOUT_SECONDS


@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/api/generate", methods=["POST"])
def generate_account():
    try:
        inbox = mailing.create_mail_inbox()
    except Exception as exc:
        return jsonify({"error": f"Could not create inbox: {exc}"}), 500

    signup = mailing.complete_boost_signup(inbox["email"], mailing.BOOST_PASSWORD)
    if not signup["ok"]:
        return jsonify({"error": signup.get("error", "Boost signup failed")}), 500

    session_id = str(uuid.uuid4())
    save_session(
        session_id,
        {
            "token": inbox["token"],
            "email": inbox["email"],
            "mail_password": inbox["mail_password"],
            "boost_password": mailing.BOOST_PASSWORD,
            "inbox_state": {
                "seen_ids": [],
                "verify_seen": False,
                "verification_link_opened": False,
                "code": None,
            },
            "watching": False,
            "finished": False,
            "finish_reason": None,
            "watch_started_at": None,
        },
    )

    return jsonify(
        {
            "sessionId": session_id,
            "email": inbox["email"],
            "boostPassword": mailing.BOOST_PASSWORD,
            "mailPassword": inbox["mail_password"],
            "name": signup.get("name"),
            "mobile": signup.get("mobile"),
        }
    )


@app.route("/api/watch/<session_id>", methods=["POST"])
def start_watch(session_id):
    session = get_session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    if session.get("finished"):
        return jsonify({"error": "Session already finished. Start over."}), 400

    session["watching"] = True
    session["finished"] = False
    session["finish_reason"] = None
    session["watch_started_at"] = time.time()
    save_session(session_id, session)
    return jsonify({"ok": True, "timeoutSeconds": WATCH_TIMEOUT_SECONDS})


@app.route("/api/stop/<session_id>", methods=["POST"])
def stop_session(session_id):
    session = get_session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404

    reason = "cancelled"
    if session.get("inbox_state", {}).get("code"):
        reason = "complete"
    stop_watching(session, reason)
    save_session(session_id, session)
    return jsonify({"ok": True, "reason": reason})


@app.route("/api/session/<session_id>", methods=["DELETE"])
def delete_session(session_id):
    with SESSION_LOCK:
        SESSIONS.pop(session_id, None)
    return jsonify({"ok": True})


@app.route("/api/status/<session_id>")
def poll_status(session_id):
    session = get_session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404

    if session.get("finished"):
        inbox_state = session.get("inbox_state", {})
        if inbox_state.get("code"):
            return jsonify(
                {
                    "status": "complete",
                    "stopped": True,
                    "code": inbox_state["code"],
                    "email": session["email"],
                    "boostPassword": session["boost_password"],
                }
            )
        if session.get("finish_reason") == "timeout":
            return jsonify(
                {
                    "status": "timeout",
                    "stopped": True,
                    "message": "No code received within 2 minutes.",
                    "email": session["email"],
                    "boostPassword": session["boost_password"],
                }
            )
        return jsonify({"status": "stopped", "stopped": True, "message": "Session ended."})

    if not session.get("watching"):
        return jsonify(
            {
                "status": "idle",
                "message": "Click “I’ve logged in — check for code” when ready.",
            }
        )

    if watch_expired(session):
        stop_watching(session, "timeout")
        save_session(session_id, session)
        return jsonify(
            {
                "status": "timeout",
                "stopped": True,
                "message": "No code received within 2 minutes.",
                "email": session["email"],
                "boostPassword": session["boost_password"],
            }
        )

    inbox_state = session["inbox_state"]
    if inbox_state.get("code"):
        stop_watching(session, "complete")
        save_session(session_id, session)
        return jsonify(
            {
                "status": "complete",
                "stopped": True,
                "code": inbox_state["code"],
                "email": session["email"],
                "boostPassword": session["boost_password"],
            }
        )

    try:
        result = mailing.poll_inbox_once(session["token"], inbox_state)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    session["inbox_state"] = {
        "seen_ids": result["seen_ids"],
        "verify_seen": result["verify_seen"],
        "verification_link_opened": result["verification_link_opened"],
        "code": result.get("code"),
    }

    if result.get("code"):
        stop_watching(session, "complete")
        save_session(session_id, session)
        return jsonify(
            {
                "status": "complete",
                "stopped": True,
                "code": result["code"],
                "email": session["email"],
                "boostPassword": session["boost_password"],
            }
        )

    save_session(session_id, session)

    if result.get("verify_link"):
        return jsonify(
            {
                "status": "verify_email",
                "message": "Verify email received — open the link in Boost, then wait for the code.",
                "verifyLink": result["verify_link"],
            }
        )

    if result["verify_seen"]:
        return jsonify(
            {
                "status": "waiting_code",
                "message": "Waiting for 6-digit code…",
                "email": session["email"],
                "boostPassword": session["boost_password"],
            }
        )

    return jsonify(
        {
            "status": "waiting_verify",
            "message": "Waiting for “Verify my account” email…",
        }
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=True)
