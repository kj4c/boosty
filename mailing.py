import json
import random
import re
import string
import time
import uuid
from datetime import date

import requests

API_URL = "https://api.mail.tm"
VERIFY_MARKER = "verify my account"

BOOST_SIGNUP_URL = "https://vibe.boostjuice.com.au/vibe/signup"
BOOST_SIGNUP_PAGE = "https://vibe.boostjuice.com.au/vibe/signup"
SIGNUP_SUBMIT_ACTION_ID = "60ede005c6e5709ed86de3269ea823482d535b055f"
SIGNUP_SUCCESS_ACTION_ID = "4054d26797aa5dc290824d2fecfcb802e03cb5306d"
BOOST_ORIGIN = "https://vibe.boostjuice.com.au"
BOOST_PASSWORD = "Abcde1234!"

_SERVER_ACTION_REF_RE = re.compile(
    r'createServerReference\)\("([a-f0-9]{40,50})"[^"]*"(onSignup(?:Submit|Success)Action)"'
)
_CHUNK_PATH_RE = re.compile(r"/_next/static/chunks/[^\"']+\.js")

FIRST_NAMES = [
    "Liam", "Noah", "Oliver", "Jack", "Henry", "Charlie", "William", "Thomas",
    "James", "Ethan", "Mia", "Olivia", "Ava", "Charlotte", "Amelia", "Sophie",
    "Isla", "Chloe", "Emily", "Ruby", "Grace", "Ella", "Zoe", "Lucy",
]
LAST_NAMES = [
    "Smith", "Jones", "Williams", "Brown", "Wilson", "Taylor", "Anderson",
    "Thomas", "White", "Martin", "Thompson", "Walker", "Harris", "Lee",
    "Ryan", "O'Brien", "Murphy", "Kelly", "King", "Wright", "Scott",
]

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-AU,en;q=0.9",
}


def generate_random_string(length=10):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


def generate_random_name():
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"


def generate_au_mobile():
    return f"+614{random.randint(10000000, 99999999)}"


def generate_dob():
    today = date.today()
    return f"{today.day:02d}-{today.month:02d}-{today.year}"


def get_domain():
    response = requests.get(f"{API_URL}/domains")
    response.raise_for_status()
    domains = response.json().get("hydra:member", [])
    return domains[0]["domain"]


def create_account(address, password):
    payload = {"address": address, "password": password}
    response = requests.post(f"{API_URL}/accounts", json=payload)
    response.raise_for_status()
    return response.json()


def get_token(address, password):
    payload = {"address": address, "password": password}
    response = requests.post(f"{API_URL}/token", json=payload)
    response.raise_for_status()
    return response.json()["token"]


def check_inbox(token):
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{API_URL}/messages", headers=headers)
    response.raise_for_status()
    return response.json().get("hydra:member", [])


def read_message(token, message_id):
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{API_URL}/messages/{message_id}", headers=headers)
    response.raise_for_status()
    return response.json()


def message_body(full_message):
    return full_message.get("text") or full_message.get("html") or ""


def extract_verification_link(body):
    match = re.search(
        r"https?://[^\s\]\)>]+email-verification\?Code=[^\s\]\)>]+",
        body,
        re.IGNORECASE,
    )
    return match.group(0) if match else None


def extract_six_digit_code(body):
    match = re.search(r"\b\d{6}\b", body)
    return match.group(0) if match else None


def follow_verification_link(url, quiet=False):
    try:
        response = requests.get(
            url,
            headers={**BROWSER_HEADERS, "Referer": BOOST_SIGNUP_PAGE},
            allow_redirects=True,
            timeout=30,
        )
        if not quiet:
            print(f"  Opened verification link (HTTP {response.status_code})")
        return response.status_code
    except requests.RequestException as exc:
        if not quiet:
            print(f"  Could not open verification link: {exc}")
        return None


def is_valid_session_token(value):
    if not value or value in ("[object Object]", "%5Bobject%20Object%5D"):
        return False
    return len(value) > 40


def signup_action_ids_stale(response):
    if response is None:
        return False
    if response.status_code == 404:
        return True
    body = (response.text or "").lower()
    return "server action not found" in body


def refresh_signup_action_ids(session=None):
    """Load current Next-Action IDs from Boost signup JS bundles."""
    global SIGNUP_SUBMIT_ACTION_ID, SIGNUP_SUCCESS_ACTION_ID

    http = session or requests.Session()
    page = http.get(BOOST_SIGNUP_PAGE, headers=BROWSER_HEADERS, timeout=30)
    if page.status_code != 200:
        return False

    submit_id = None
    success_id = None
    for path in dict.fromkeys(_CHUNK_PATH_RE.findall(page.text)):
        chunk_url = f"{BOOST_ORIGIN}{path}".replace("&amp;", "")
        try:
            chunk = http.get(chunk_url, headers=BROWSER_HEADERS, timeout=20)
        except requests.RequestException:
            continue
        if chunk.status_code != 200:
            continue
        for action_hash, action_name in _SERVER_ACTION_REF_RE.findall(chunk.text):
            if action_name == "onSignupSubmitAction":
                submit_id = action_hash
            elif action_name == "onSignupSuccessAction":
                success_id = action_hash
        if submit_id and success_id:
            break

    if not submit_id or not success_id:
        return False

    SIGNUP_SUBMIT_ACTION_ID = submit_id
    SIGNUP_SUCCESS_ACTION_ID = success_id
    return True


def create_boost_session():
    device_id = str(uuid.uuid4())
    session = requests.Session()
    session.cookies.set("RZBUDI", device_id, domain="vibe.boostjuice.com.au")
    session.get(BOOST_SIGNUP_PAGE, headers=BROWSER_HEADERS, timeout=30)
    clear_invalid_session_cookie(session)
    if not session.cookies.get("RZBUDI"):
        session.cookies.set("RZBUDI", device_id, domain="vibe.boostjuice.com.au")
    session.device_id = device_id
    return session


def signup_request_headers(action_id):
    return {
        **BROWSER_HEADERS,
        "Next-Action": action_id,
        "Accept": "text/x-component",
        "Content-Type": "text/plain;charset=UTF-8",
        "Origin": "https://vibe.boostjuice.com.au",
        "Referer": BOOST_SIGNUP_PAGE,
    }


def clear_invalid_session_cookie(session):
    if not is_valid_session_token(session.cookies.get("_RZ_SESSION")):
        session.cookies.pop("_RZ_SESSION", None)


def build_signup_metadata(session):
    return {
        "x-rz-platform": "web",
        "x-rz-app-version": "5.0.0",
        "x-rz-unique-device-id": session.device_id,
        "x-rz-origin": "boost:website",
        "x-rz-device-type": "Macintosh:Apple",
        "x-rz-device-name": "Chrome:148.0.0.0",
    }


def parse_step1_session_message(response_text):
    match = re.search(
        r'1:\s*(\{"action"\s*:\s*"success"\s*,\s*"message"\s*:\s*"([^"]+)"\s*\})',
        response_text,
    )
    if match:
        return match.group(2)
    match = re.search(r'"action"\s*:\s*"success"\s*,\s*"message"\s*:\s*"([^"]+)"', response_text)
    return match.group(1) if match else None


def parse_step1_error_message(response_text):
    match = re.search(
        r'"action"\s*:\s*"(?:default|error)"\s*,\s*"message"\s*:\s*"([^"]+)"',
        response_text,
    )
    return match.group(1) if match else None


def boost_signup_step1(session, email, password, name, mobile, dob):
    payload_data = [
        build_signup_metadata(session),
        {
            "dateOfBirth": dob,
            "email": email,
            "memberNo": "",
            "mobile": mobile,
            "name": name,
            "password": password,
            "sendEmail": "false",
            "sendSms": "false",
            "verifyPIN": "",
        },
    ]
    clear_invalid_session_cookie(session)
    response = session.post(
        BOOST_SIGNUP_URL,
        data=json.dumps(payload_data),
        headers=signup_request_headers(SIGNUP_SUBMIT_ACTION_ID),
        timeout=30,
    )
    return response


def boost_signup_step2(session, session_message):
    clear_invalid_session_cookie(session)
    return session.post(
        BOOST_SIGNUP_URL,
        data=session_message,
        headers=signup_request_headers(SIGNUP_SUCCESS_ACTION_ID),
        timeout=30,
    )


def get_session_token(session):
    token = session.cookies.get("_RZ_SESSION", "")
    return token if is_valid_session_token(token) else None


def _retry_signup_step_if_stale(session, response, retry_fn):
    if signup_action_ids_stale(response) and refresh_signup_action_ids(session):
        return retry_fn()
    return response


def run_boost_signup(session, email, boost_password, name, mobile, dob):
    response1 = boost_signup_step1(session, email, boost_password, name, mobile, dob)
    response1 = _retry_signup_step_if_stale(
        session,
        response1,
        lambda: boost_signup_step1(
            session, email, boost_password, name, mobile, dob
        ),
    )

    if response1.status_code != 200:
        detail = (response1.text or "").strip()[:120]
        return False, f"signup request failed (HTTP {response1.status_code}: {detail})"

    token = get_session_token(session)
    if token:
        return True, name

    session_message = parse_step1_session_message(response1.text)
    if not session_message:
        err = parse_step1_error_message(response1.text) or "signup failed"
        return False, err

    response2 = boost_signup_step2(session, session_message)
    response2 = _retry_signup_step_if_stale(
        session,
        response2,
        lambda: boost_signup_step2(session, session_message),
    )
    if get_session_token(session):
        return True, name

    # Account is created after step 1; continue even if cookie sync fails
    if response2.status_code == 200 or session_message:
        return True, name

    return False, "could not complete signup"


def complete_boost_signup(email, boost_password=BOOST_PASSWORD, max_attempts=15):
    """Register with Boost; returns {ok, name?, mobile?, error?}."""
    for attempt in range(1, max_attempts + 1):
        name = generate_random_name()
        mobile = generate_au_mobile()
        dob = generate_dob()
        session = create_boost_session()
        try:
            ok, detail = run_boost_signup(
                session, email, boost_password, name, mobile, dob
            )
        except requests.RequestException as exc:
            if attempt == max_attempts:
                return {"ok": False, "error": str(exc)}
            time.sleep(2)
            continue

        if ok:
            return {"ok": True, "name": detail, "mobile": mobile}

        if "already been registered" in str(detail).lower():
            return {"ok": True, "name": None, "mobile": None, "already_registered": True}

        detail_lower = str(detail).lower()
        if "server action not found" in detail_lower or "http 404" in detail_lower:
            refresh_signup_action_ids()

        if attempt == max_attempts:
            return {"ok": False, "error": detail}
        time.sleep(2)

    return {"ok": False, "error": "signup failed"}


def retry_boost_signup(email, boost_password):
    print("\nSigning up with Boost...")
    result = complete_boost_signup(email, boost_password)
    if result["ok"]:
        if result.get("name"):
            print(f"  Registered as {result['name']} | {result['mobile']}")
        return True
    print(f"  {result.get('error', 'signup failed')}")
    return False


def print_credentials(email, boost_password, mail_password=None):
    print(f"  Boost — email: {email}  password: {boost_password}")
    if mail_password:
        print(f"  Mail.tm inbox — email: {email}  password: {mail_password}")


def poll_inbox_once(token, state):
    """
    Check inbox once. state keys: seen_ids (list), verify_seen, verification_link_opened, code.
    Returns updated state plus optional code and verify_link.
    """
    if state.get("code"):
        return {**state, "verify_link": None}

    seen_ids = set(state.get("seen_ids", []))
    verify_seen = state.get("verify_seen", False)
    verification_link_opened = state.get("verification_link_opened", False)
    code = None
    verify_link = None

    messages = check_inbox(token)
    messages.sort(key=lambda m: m.get("createdAt", ""))

    for msg in messages:
        message_id = msg["id"]
        if message_id in seen_ids:
            continue

        full_message = read_message(token, message_id)
        body = message_body(full_message)

        if not verify_seen and VERIFY_MARKER in body.lower():
            link = extract_verification_link(body)
            if link:
                verify_link = link
                if not verification_link_opened:
                    follow_verification_link(link, quiet=True)
                    verification_link_opened = True
            verify_seen = True
            seen_ids.add(message_id)
            continue

        if verify_seen and not code:
            found = extract_six_digit_code(body)
            if found:
                code = found
            seen_ids.add(message_id)
            continue

        if not verify_seen:
            seen_ids.add(message_id)

    return {
        "seen_ids": list(seen_ids),
        "verify_seen": verify_seen,
        "verification_link_opened": verification_link_opened,
        "code": code,
        "verify_link": verify_link,
    }


def process_inbox(token, seen_ids, verify_seen, code_found, verification_link_opened):
    state = poll_inbox_once(
        token,
        {
            "seen_ids": list(seen_ids),
            "verify_seen": verify_seen,
            "verification_link_opened": verification_link_opened,
            "code": "__done__" if code_found else None,
        },
    )
    code = state.get("code")
    has_code = code_found or (code and code != "__done__")
    if state.get("verify_link"):
        print("\nVerify email — link opened")
        print(f"  {state['verify_link']}")
    if code and code != "__done__":
        print(f"\n6-digit code: {code}")
    return state["verify_seen"], has_code, state["verification_link_opened"]


def watch_inbox(token, email, boost_password, mail_password=None):
    print("\nWaiting for verification emails (Ctrl+C to stop)...")
    print_credentials(email, boost_password, mail_password)

    seen_ids = set()
    verify_seen = False
    code_found = False
    verification_link_opened = False
    reminded_credentials = False

    try:
        while True:
            verify_seen, code_found, verification_link_opened = process_inbox(
                token, seen_ids, verify_seen, code_found, verification_link_opened
            )

            if code_found:
                print("\nFinished.")
                return

            if not verify_seen:
                print("  Waiting for 'Verify my account' email...")
            elif not code_found:
                if not reminded_credentials:
                    print("\n  Click the link above, then enter the code in Boost.")
                    print_credentials(email, boost_password, mail_password)
                    reminded_credentials = True
                else:
                    print("  Waiting for 6-digit code...")

            time.sleep(5)
    except KeyboardInterrupt:
        print("\nStopped.")


def create_mail_inbox():
    domain = get_domain()
    username = generate_random_string(8)
    mail_password = generate_random_string(12)
    email = f"{username}@{domain}"
    create_account(email, mail_password)
    token = get_token(email, mail_password)
    return {"email": email, "mail_password": mail_password, "token": token}


def setup_mail_account():
    print("Creating temporary inbox...")
    inbox = create_mail_inbox()
    print(f"  Inbox ready: {inbox['email']}")
    return inbox["email"], inbox["mail_password"], inbox["token"]


def run_automated_flow():
    email, mail_password, token = setup_mail_account()
    retry_boost_signup(email, BOOST_PASSWORD)
    watch_inbox(token, email, BOOST_PASSWORD, mail_password)


def main():
    print("Boost Juice Signup + Mail.tm")
    print("1. Full flow (new email → signup → verify)")
    print("2. Existing Mail.tm inbox only")
    choice = input("Option (1 or 2): ").strip()

    if choice == "1":
        run_automated_flow()
    elif choice == "2":
        email = input("Email: ").strip()
        mail_password = input("Mail.tm password: ").strip()
        try:
            token = get_token(email, mail_password)
            print(f"Logged in as {email}")
        except requests.exceptions.HTTPError:
            print("Mail.tm login failed.")
        else:
            retry_boost_signup(email, BOOST_PASSWORD)
            watch_inbox(token, email, BOOST_PASSWORD, mail_password)
    else:
        print("Invalid option.")


if __name__ == "__main__":
    main()
