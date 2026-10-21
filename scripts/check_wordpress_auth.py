"""GET-only diagnosis; prints allowlisted error codes, never provider messages."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.store_config import StoreSettings, COMPANIES
from app.services.store_http import http_client


def main():
    settings = StoreSettings()
    allowed = {"incorrect_password", "invalid_username", "invalid_email",
               "application_passwords_disabled", "application_passwords_disabled_for_user",
               "rest_not_logged_in", "rest_forbidden_context", "invalid_application_password"}
    print(json.dumps({"organization_binding_configured": bool(settings.organization_id)}))
    for company in COMPANIES:
        try:
            credentials = settings.credentials(company, "wp")
            with http_client(credentials.base_url, "wp/v2",
                             auth=(credentials.username, credentials.password),
                             timeout=settings.timeout) as client:
                response = client.get("users/me", params={"context": "edit", "_fields": "id"})
                try:
                    body = response.json()
                    code = body.get("code") if isinstance(body, dict) else None
                except ValueError:
                    code = None
                print(json.dumps({"company": company, "http_status": response.status_code,
                                  "error_code": code if code in allowed else "other_or_unavailable"}))
        except Exception:
            print(json.dumps({"company": company, "status": "configuration_or_connection_error"}))


if __name__ == "__main__":
    main()
