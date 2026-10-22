"""Local operator diagnostic: GET only; prints no credentials or product data."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.store_config import COMPANIES, StoreSettings
from app.services.store_connections import check_company
from app.services.store_http import http_client, read_json, StoreAPIError


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--company", choices=COMPANIES)
    parser.add_argument("--public", action="store_true", help="Sonda sem credenciais; nunca comprova autenticação")
    args = parser.parse_args()
    settings = StoreSettings()
    companies = [args.company] if args.company else COMPANIES
    if args.public:
        results = []
        for company in companies:
            for api, endpoint in (("wc/v3","products"),("wp/v2","users/me")):
                record = {"company":company, "api":api, "authenticated":False, "anonymous_probe":True}
                try:
                    with http_client(getattr(settings, company+"_url"), api, timeout=settings.timeout) as client:
                        read_json(client, endpoint, {"context":"edit","per_page":1,"_fields":"id"})
                    record.update(http_status=200, status="public_response_not_authentication")
                except StoreAPIError as exc:
                    record.update(http_status=exc.status, status=exc.code, message=str(exc))
                except ValueError:
                    record.update(status="invalid_configuration")
                results.append(record)
        print(json.dumps({"public_checks":results}, ensure_ascii=True, indent=2))
        return 0
    results = [check_company(company, settings) for company in companies]
    print(json.dumps({"checks":results}, ensure_ascii=True, indent=2))
    # CLI does not impersonate a PRM user or persist UI history.
    return 0 if all(r["woocommerce"]["authenticated"] and r["wordpress"]["authenticated"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
