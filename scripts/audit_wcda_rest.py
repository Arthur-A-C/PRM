"""Bounded REST GET-only investigation. Logs shapes, never URLs/credentials/values."""
import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.services.store_config import StoreSettings,COMPANIES
from app.services.registration_woo_api import WooClient,credentials_for
from app.services.store_http import http_client,read_json,StoreAPIError
from app.services.store_documents import interpret_documents


def audit(company,settings,pages=10,transport=None):
    wc=WooClient(credentials_for(company,settings),transport=transport,timeout=settings.timeout)
    wp=settings.credentials(company,"wp")
    report={"company":company,"checked_at":datetime.now(timezone.utc).isoformat(),
            "method":"GET","products_scanned":0,"with_documents":0,"empty_fields":0,
            "absent_fields":0,"malformed_products":0,"scan_stop":"page_limit",
            "examples":[],"rest_index":{},"write_support":"not_verified"}
    keys=Counter();types={};identifiers=set();orders=set()
    try:
        for page in range(1,pages+1):
            rows=wc.products(page=page,per_page=100,_fields="id,meta_data",orderby="id",order="asc")
            report["products_scanned"]+=len(rows)
            for row in rows:
                interpreted=interpret_documents(row)
                if interpreted["warnings"]: report["malformed_products"]+=1
                if not interpreted["present"]: report["absent_fields"]+=1
                elif not interpreted["documents"]: report["empty_fields"]+=1
                else:
                    report["with_documents"]+=1
                    for doc in interpreted["documents"]:
                        identifiers.update(doc["identifier_candidates"])
                        orders.update(doc["explicit_order_candidates"])
                        for key,value in doc["raw"].items():
                            keys[key]+=1;types.setdefault(key,set()).add(type(value).__name__)
                    if len(report["examples"])<3:
                        report["examples"].append({"product_id":row["id"],"document_count":len(interpreted["documents"]),
                            "metadata_id_present":all(d["metadata_id"] is not None for d in interpreted["documents"]),
                            "entry_keys":sorted({k for d in interpreted["documents"] for k in d["raw"]})})
            if report["with_documents"]>=3:
                report["scan_stop"]="three_nonempty_products_found";break
            if len(rows)<100:
                report["scan_stop"]="end_of_catalog";break
            if transport is None: time.sleep(.3)
        report["field_types"]={k:sorted(v) for k,v in types.items()}
        report["identifier_candidates"]=sorted(identifiers);report["explicit_order_candidates"]=sorted(orders)
        # Publicly advertised route methods/arguments are declarations, NOT write tests.
        with http_client(wp.base_url,"",auth=(wp.username,wp.password),timeout=settings.timeout,transport=transport) as client:
            try:
                index=read_json(client,"")
                routes=index.get("routes",{}) if isinstance(index,dict) else {}
                relevant={}
                for route,description in routes.items():
                    if any(term in route.lower() for term in ("wcda","download","arquivo")) or route=="/wc/v3/products/(?P<id>[\\d]+)":
                        if isinstance(description,dict):
                            relevant[route]={"methods":description.get("methods",[]),
                                "metadata_argument_declared":any("meta_data" in e.get("args",{}) for e in description.get("endpoints",[]) if isinstance(e,dict)),
                                "wcda_literal_in_route_description":"wcda_arquivos" in json.dumps(description)}
                report["rest_index"]={"status":"ok","relevant_routes":relevant,
                    "wcda_literal_anywhere":"wcda_arquivos" in json.dumps(routes),
                    "total_routes":len(routes)}
            except (StoreAPIError,ValueError) as exc:
                report["rest_index"]={"status":exc.code if isinstance(exc,StoreAPIError) else "invalid_response"}
        # Look up existing media by filename, then require exact source_url match.
        # No document URL is fetched. These IDs are observed relations, not stored IDs.
        if report["examples"]:
            product=wc.product(report["examples"][0]["product_id"])
            docs=interpret_documents(product)["documents"]
            relations=[]
            with http_client(wp.base_url,"wp/v2",auth=(wp.username,wp.password),timeout=settings.timeout,transport=transport) as client:
                for doc in docs[:2]:
                    filename=doc.get("filename")
                    if not isinstance(filename,str) or not filename or len(filename)>250: continue
                    try:
                        media=read_json(client,"media",{"context":"edit","search":filename,"per_page":10,"_fields":"id,source_url"})
                        matches=[m for m in media if isinstance(m,dict) and m.get("source_url")==doc["url"]] if isinstance(media,list) else []
                        relations.append({"document_position":doc["position"],"exact_media_url_matches":len(matches),
                            "attachment_id_stored_in_wcda":bool(doc["identifier_candidates"])})
                    except (StoreAPIError,ValueError):
                        relations.append({"document_position":doc["position"],"media_lookup":"unavailable"})
            report["media_relations"]=relations
    except (StoreAPIError,ValueError):
        report["scan_stop"]="request_failed"
    finally: wc.close()
    return report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--pages",type=int,default=10,choices=range(1,21))
    parser.add_argument("--company",choices=COMPANIES)
    args=parser.parse_args();settings=StoreSettings()
    for company in ([args.company] if args.company else COMPANIES):
        print(json.dumps(audit(company,settings,args.pages),ensure_ascii=True),flush=True)


if __name__=="__main__": main()
