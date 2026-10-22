"""Read-only audit: organization IDs and structural metadata only, no file URLs."""
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from app.db import get_engine
from app.models import Organization, Company
from app.services.store_config import StoreSettings, COMPANIES
from app.services.registration_woo_api import WooClient, credentials_for


def shape(value, depth=0):
    if depth > 4:
        return type(value).__name__
    if isinstance(value, dict):
        return {str(k)[:80]:shape(v,depth+1) for k,v in value.items()}
    if isinstance(value, list):
        return {"type":"list","length":len(value),"sample_shapes":[shape(v,depth+1) for v in value[:2]]}
    if isinstance(value,str):
        if value.startswith(("https://","http://")):
            return {"type":"url","extension":Path(urlsplit(value).path).suffix[:12]}
        return "numeric_string" if value.isdecimal() else "string"
    return type(value).__name__


def main():
    try:
        with get_engine().connect() as db:
            print(json.dumps({"organizations":[{"id":str(row.id),"name":row.name} for row in db.execute(select(Organization.id,Organization.name))],
                              "companies":[{"code":row.code,"organization_id":str(row.organization_id)} for row in db.execute(select(Company.code,Company.organization_id))]},ensure_ascii=True))
    except Exception:
        print(json.dumps({"database_audit":"unavailable"}))
    settings=StoreSettings()
    for company in COMPANIES:
        client=None
        try:
            client=WooClient(credentials_for(company,settings))
            products=client.products(per_page=5,_fields="id,meta_data")
            fields=[shape(item["value"]) for p in products for item in p.get("meta_data",[])
                    if item.get("key")=="_wcda_arquivos"]
            print(json.dumps({"company":company,"products_sampled":len(products),"wcda_shapes":fields},ensure_ascii=True))
        except Exception:
            print(json.dumps({"company":company,"audit":"failed"}))
        finally:
            if client: client.close()


if __name__=="__main__":
    main()
