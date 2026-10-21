"""Staging-only file publisher: product images and _wcda_arquivos, never commercial fields.

Existing read-only clients remain read-only. Production hosts are refused by policy.
Ambiguous HTTP writes are journaled and never retried blindly; media is never deleted.
"""
import hashlib
import json
import mimetypes
from pathlib import Path
from urllib.parse import urlsplit, unquote

import httpx
from PIL import Image
import io
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.services.store_config import ROOT, secure_url
from app.services.store_http import http_client, read_json
from app.services.registration_woo_api import WooClient, credentials_for
from app.services.store_document_update import _protected, known_media_document, prepare_document_update
from app.services.store_registration_plan import WRITABLE_KEYS, format_filesize, has_identity, identity, upload_name

PRODUCTION_HOSTS = {"choicetech.com.br","sagloja.devsplcomunic.com.br","portwell.com.br"}
MIMES = {".png":"image/png",".jpg":"image/jpeg",".jpeg":"image/jpeg",".webp":"image/webp",
         ".pdf":"application/pdf",".zip":"application/zip"}


class PublishSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT/".env",extra="ignore",env_prefix="PRM_PUBLISH_")
    enabled: bool = False
    staging_origin: str = ""
    staging_sku: str = ""
    storage_dir: str = "data/store_publish"
    max_file_mib: int = Field(20,ge=1,le=100)

    def authorize(self, origin, sku):
        if not self.enabled:
            raise ValueError("Gravação desabilitada; configure homologação em staging.")
        origin = secure_url(origin)
        if origin != self.staging_origin.rstrip("/") or sku != self.staging_sku:
            raise ValueError("Origem/SKU fora da homologação autorizada.")
        if urlsplit(origin).hostname in PRODUCTION_HOSTS:
            raise ValueError("Gravação nas três lojas atuais bloqueada nesta etapa.")


def file_info(path, limit_mib=20):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= limit_mib*1024**2:
        raise ValueError("Arquivo ausente, link ou tamanho não permitido.")
    suffix=path.suffix.lower()
    if suffix not in MIMES:
        raise ValueError("Formato não homologado: "+suffix)
    raw=path.read_bytes()
    if suffix in {".png",".jpg",".jpeg",".webp"}:
        with Image.open(io.BytesIO(raw)) as im:
            if im.width*im.height > 40_000_000:
                raise ValueError("Imagem excede limite de pixels.")
            expected={".png":"PNG",".jpg":"JPEG",".jpeg":"JPEG",".webp":"WEBP"}[suffix]
            if im.format != expected:
                raise ValueError("Extensão não corresponde à imagem.")
            im.verify()
    elif suffix==".pdf" and not raw.startswith(b"%PDF-"):
        raise ValueError("PDF inválido.")
    elif suffix==".zip" and not raw.startswith(b"PK"):
        raise ValueError("ZIP inválido.")
    return {"sha256":hashlib.sha256(raw).hexdigest(),"bytes":len(raw),"mime":MIMES[suffix],"name":path.name}


def product_snapshot(product):
    return {"id":product["id"],"sku":product.get("sku"),
            "images":product.get("images",[]),
            "wcda":[i for i in product.get("meta_data",[]) if i.get("key")=="_wcda_arquivos"]}


def snapshot_hash(product):
    return hashlib.sha256(json.dumps(product_snapshot(product),sort_keys=True).encode()).hexdigest()


class StagingPublisher:
    def __init__(self, company, sku, settings, policy, journal, *, transport=None):
        self.company,self.sku,self.policy,self.journal=company,sku,policy,journal
        wc=credentials_for(company,settings)
        policy.authorize(wc.base_url,sku)
        wp=settings.credentials(company,"wp")
        self.woo=WooClient(wc,transport=transport,timeout=settings.timeout)
        self.wp=http_client(wp.base_url,"wp/v2",auth=(wp.username,wp.password),transport=transport,timeout=settings.timeout)

    def close(self):
        self.woo.close();self.wp.close()

    def library_match(self, sha):
        """Media identity lookup: a prior upload of the same bytes carries prm-<sha16> in its URL."""
        rows=read_json(self.wp,"media",{"search":identity(sha),"per_page":20,"context":"edit"})
        if not isinstance(rows,list): raise ValueError("Resposta da biblioteca de mídia inválida.")
        found=[r for r in rows if isinstance(r,dict) and has_identity(r.get("source_url"),sha)
               and type(r.get("id")) is int and r["id"]>0]
        if len(found)>1: raise ValueError("Mais de uma mídia com o mesmo hash; reconciliar manualmente.")
        return {"id":found[0]["id"],"source_url":found[0]["source_url"]} if found else None

    def upload(self, path, expected):
        current=file_info(path,self.policy.max_file_mib)
        if current["sha256"]!=expected["sha256"]:
            raise ValueError("Arquivo mudou após a prévia.")
        key=current["sha256"]
        saved=self.journal.get(key)
        if saved and saved["state"]=="done":
            return {**saved["media"],"reused":"journal"}
        # A lost response is resolved only by finding the exact identity in the library; never resend blindly.
        found=self.library_match(key)
        if found:
            self.journal.put(key,{"state":"done","media":found})
            return {**found,"reused":"library"}
        if saved and saved["state"]!="rejected":
            raise ValueError("Upload anterior incerto; reconciliação manual necessária.")
        # Persist BEFORE sending. Crash between response and save cannot duplicate on retry.
        self.journal.put(key,{"state":"sending"})
        name=upload_name(expected["name"],key,expected.get("role","gallery"))
        try:
            with open(path,"rb") as handle:
                response=self.wp.post("media",files={"file":(name,handle,current["mime"])},
                                      data={"title":Path(expected["name"]).stem})
            if response.status_code!=201:
                # Explicit refusal: a later retry may resend, after the library identity check above.
                self.journal.put(key,{"state":"rejected","status":response.status_code})
                raise ValueError("Upload recusado; verificar permissões/formato. Sem retry automático.")
            result=response.json()
            if type(result.get("id")) is not int or result["id"]<=0 or not result.get("source_url"):
                raise ValueError("Resposta de upload inválida.")
            media={"id":result["id"],"source_url":result["source_url"]}
            self.journal.put(key,{"state":"done","media":media})
            return {**media,"reused":None}
        except Exception:
            raise ValueError("Upload não confirmado; verificar antes de reprocessar.") from None

    def execute(self, plan, *, audit=lambda event, detail=None: None):
        """Files only: one PUT limited to images and the existing _wcda_arquivos metadata."""
        dry=plan["dry_run"];approval=plan.get("approval") or {}
        if approval.get("dry_run_sha256")!=dry["dry_run_sha256"]:
            raise ValueError("Dry Run não aprovado ou alterado após a aprovação.")
        if dry["blockers"]:
            raise ValueError("Dry Run com bloqueios; nada enviado.")
        product=self.woo.find_by_sku(self.sku)
        if not product or product["id"]!=plan["product_id"] or product.get("sku")!=self.sku:
            raise ValueError("Produto/SKU não corresponde à prévia.")
        update_key="files:"+str(product["id"])+":"+dry["dry_run_sha256"]
        previous=self.journal.get(update_key)
        if previous:
            if previous["state"]=="done" or self.matches(product,previous):
                self.journal.put(update_key,{**previous,"state":"done"})
                return {"status":"done","verified":True,"reconciled":True}
            raise ValueError("Atualização anterior incerta; reconciliar antes de tentar novamente.")
        if snapshot_hash(product)!=plan["snapshot_hash"]:
            raise ValueError("Produto alterado desde a prévia; refaça a prévia.")
        # Plan files and Dry Run actions come from the same ordered list; identical bytes may repeat.
        if len(plan["images"])!=len(dry["images"]["actions"]) or len(plan["downloads"])!=len(dry["documents"]["actions"]):
            raise ValueError("Plano de arquivos inconsistente com o Dry Run.")
        images=[i for i,a in zip(plan["images"],dry["images"]["actions"]) if a["action"]=="upload" and a["sha256"]==i["sha256"]]
        documents=[d for d,a in zip(plan["downloads"],dry["documents"]["actions"]) if a["action"]=="add" and a["sha256"]==d["sha256"]]
        uploaded={}
        # Partial failure keeps every confirmed upload in the journal; a retry reuses them.
        for item in images+documents:
            media=self.upload(item["path"],item)
            uploaded[item["sha256"]]=media
            audit("upload_reused" if media["reused"] else "upload_done",{"name":item["name"],"media_id":media["id"]})
        fresh=self.woo.product(product["id"])
        if snapshot_hash(fresh)!=plan["snapshot_hash"]:
            raise ValueError("Alteração concorrente detectada; mídia enviada preservada para reconciliação.")
        before_wcda=product_snapshot(fresh)["wcda"]
        payload={}
        if images:
            ids=[i["id"] for i in fresh.get("images",[]) if type(i.get("id")) is int]
            new=[uploaded[i["sha256"]]["id"] for i in images]
            main=next((uploaded[i["sha256"]]["id"] for i in images if i["role"]=="main_image"),None)
            # Existing main image stays primary unless replacement was explicitly approved; nothing is removed.
            order=[main]+ids+new if approval.get("replace_main") and main and ids else ids+new
            payload["images"]=[{"id":i} for i in dict.fromkeys(order)]
        if documents:
            entries=[known_media_document(d["label"],Path(unquote(urlsplit(uploaded[d["sha256"]]["source_url"]).path)).name,
                                          format_filesize(d["bytes"]),uploaded[d["sha256"]]) for d in documents]
            document_plan=prepare_document_update(self.company,self.woo.credentials.base_url,fresh,self.sku,entries,
                                                  allow_empty=dry["documents"]["mode"]=="first_inclusion")
            payload["meta_data"]=document_plan.payload["meta_data"]
        if not payload or not set(payload)<=WRITABLE_KEYS:
            raise ValueError("Payload fora do escopo de arquivos; nada enviado.")
        expected={"images":[i["id"] for i in payload.get("images",fresh.get("images",[]))],
                  "wcda":payload["meta_data"][0]["value"] if documents else before_wcda[0]["value"] if before_wcda else None,
                  "protected":_protected_hash(fresh)}
        # Recovery restores only the two file keys; uploaded media stays in the library.
        rollback={"images":[{"id":i.get("id")} for i in fresh.get("images",[])],
                  "meta_data":[{"id":m.get("id"),"key":m.get("key"),"value":m.get("value")} for m in before_wcda],
                  "media_uploaded":[m["id"] for m in uploaded.values()],"media_deletion":False}
        self.journal.put(update_key,{"state":"sending",**expected,"rollback":rollback})
        audit("put_sent",{"keys":sorted(payload)})
        try:
            status=self.woo.client.put(f"products/{product['id']}",json=payload).status_code
        except httpx.RequestError:
            status=None
        try:
            verified=self.woo.product(product["id"])
        except Exception:
            verified=None
        # A lost response (no status) is accepted only when the read-back equals the exact expected state.
        if status not in {200,None} or not verified or not self.matches(verified,expected):
            raise ValueError("Atualização não confirmada pela releitura; sem retry automático. Plano de recuperação no journal.")
        self.journal.put(update_key,{"state":"done",**expected,"rollback":rollback})
        audit("verified",{"images":len(expected["images"]),"documents":len(expected["wcda"] or [])})
        return {"status":"done","verified":True,"images":expected["images"],"documents_added":len(documents),
                "uploads":[{"media_id":m["id"],"reused":m["reused"]} for m in uploaded.values()],"rollback":rollback}

    @staticmethod
    def matches(product, expected):
        wcda=product_snapshot(product)["wcda"]
        return ([i.get("id") for i in product.get("images",[])]==expected["images"]
                and (wcda[0]["value"] if wcda else None)==expected["wcda"]
                and _protected_hash(product)==expected["protected"])


def _protected_hash(product):
    # Every commercial field and every other metadata must be identical after the file PUT.
    protected={k:v for k,v in _protected(product).items() if k!="images"}
    return hashlib.sha256(json.dumps(protected,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
