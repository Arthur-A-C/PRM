"""File publisher: product images and _wcda_arquivos, never commercial fields.

The normal registration queue supplies a fresh active-role/organization/Dry Run confirmation check.
Legacy direct callers still follow PublishSettings or a scoped grant; no global policy bypass.
WooCommerce writes use the WordPress application password, whose capabilities are verified
before the first upload. Ambiguous HTTP writes are journaled and never retried blindly;
media is never deleted.
"""
import hashlib
import json
import re
import mimetypes
from pathlib import Path
from urllib.parse import urlsplit, unquote

import httpx
from PIL import Image
import io
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.services.store_config import ROOT, secure_url
from app.services.upload_limits import DEFAULT_FILE_MIB, check_size, file_hash
from app.services.store_http import http_client, read_json
from app.services.registration_woo_api import WooClient, WooCredentials, credentials_for
from app.services import store_publish_grant as grants
from app.services.store_document_update import _protected, known_media_document, prepare_document_update
from app.services.store_registration_plan import WRITABLE_KEYS, check_scope, format_filesize, has_identity, identity, scoped_order, stale_supplier_datasheet, upload_name

PRODUCTION_HOSTS = {"choicetech.com.br","sagloja.devsplcomunic.com.br","portwell.com.br"}
MIMES = {".png":"image/png",".jpg":"image/jpeg",".jpeg":"image/jpeg",".webp":"image/webp",
         ".pdf":"application/pdf",".zip":"application/zip"}


class PublishSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT/".env",extra="ignore",env_prefix="PRM_PUBLISH_",populate_by_name=True)
    enabled: bool = False
    staging_origin: str = ""
    staging_sku: str = ""
    storage_dir: str = "data/store_publish"
    max_file_mib: int = Field(DEFAULT_FILE_MIB,ge=1,le=1024,validation_alias="PRM_UPLOAD_MAX_FILE_MIB")
    # Whole ZIP/folder, same variable as the browser uploads (Settings.upload_max_mib).
    max_package_mib: int = Field(2048,ge=1,le=20480,validation_alias="PRM_UPLOAD_MAX_MIB")
    upload_timeout_seconds: int = Field(1800,ge=60,le=7200)

    def authorize(self, origin, sku):
        if not self.enabled:
            raise ValueError("Gravação desabilitada; configure homologação em staging.")
        origin = secure_url(origin)
        if origin != self.staging_origin.rstrip("/") or sku != self.staging_sku:
            raise ValueError("Origem/SKU fora da homologação autorizada.")
        if urlsplit(origin).hostname in PRODUCTION_HOSTS:
            raise ValueError("Gravação nas três lojas atuais bloqueada nesta etapa.")


def file_info(path, limit_mib=DEFAULT_FILE_MIB):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size:
        raise ValueError("Arquivo ausente, link ou tamanho não permitido.")
    check_size(path.stat().st_size, limit_mib)
    suffix=path.suffix.lower()
    if suffix not in MIMES:
        raise ValueError("Formato não homologado: "+suffix)
    with path.open('rb') as handle: raw=handle.read(16)
    if suffix in {".png",".jpg",".jpeg",".webp"}:
        with Image.open(path) as im:
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
    return {"sha256":file_hash(path),"bytes":path.stat().st_size,"mime":MIMES[suffix],"name":path.name}


def product_snapshot(product):
    return {"id":product["id"],"sku":product.get("sku"),
            "images":product.get("images",[]),
            "wcda":[i for i in product.get("meta_data",[]) if i.get("key")=="_wcda_arquivos"]}


def snapshot_hash(product):
    return hashlib.sha256(json.dumps(product_snapshot(product),sort_keys=True).encode()).hexdigest()


REQUIRED_CAPABILITIES = ("upload_files","edit_products","edit_published_products","edit_others_products")


class StagingPublisher:
    def __init__(self, company, sku, settings, policy, journal, *, transport=None, grant=None, authorization_check=None):
        self.company,self.sku,self.policy,self.journal,self.grant=company,sku,policy,journal,grant
        self.authorization_check = authorization_check
        wc=credentials_for(company,settings)
        wp=settings.credentials(company,"wp")
        if secure_url(wp.base_url)!=secure_url(wc.base_url):
            raise ValueError("WordPress e WooCommerce com origens diferentes; gravação recusada.")
        if authorization_check is not None:
            authorization_check()
        elif grant:
            grants.check(grant,company=company,origin=wc.base_url,sku=sku)
        else:
            policy.authorize(wc.base_url,sku)
        # Writes authenticate as the WordPress application-password user: capabilities are inspectable.
        self.woo=WooClient(WooCredentials(wp.base_url,wp.username,wp.password),transport=transport,timeout=settings.timeout)
        self.wp=http_client(wp.base_url,"wp/v2",auth=(wp.username,wp.password),transport=transport,timeout=settings.timeout)

    def close(self):
        self.woo.close();self.wp.close()

    def verify_permissions(self, product_id):
        """Read-only proof (GET users/me + OPTIONS Allow) that this user may upload media and edit this product."""
        me=read_json(self.wp,"users/me",{"context":"edit","_fields":"id,capabilities"})
        caps=me.get("capabilities") if isinstance(me,dict) else None
        if not isinstance(caps,dict): raise ValueError("Capacidades do usuário WordPress indisponíveis.")
        missing=[c for c in REQUIRED_CAPABILITIES if caps.get(c) is not True]
        allow=lambda response:{m.strip().upper() for m in response.headers.get("allow","").split(",") if m.strip()} if response.status_code==200 else set()
        product_allow=allow(self.woo.client.options(f"products/{product_id}"))
        media_allow=allow(self.wp.options("media"))
        if "PUT" not in product_allow: missing.append(f"PUT products/{product_id}")
        if "POST" not in media_allow: missing.append("POST media")
        if missing:
            raise ValueError("Permissões insuficientes para gravação: "+", ".join(missing)+". Nada enviado.")
        return {"user_id":me.get("id"),"capabilities":list(REQUIRED_CAPABILITIES),
                "product_allow":sorted(product_allow),"media_allow":sorted(media_allow)}

    def library_match(self, sha):
        """Media identity lookup: a prior upload of the same bytes carries prm-<sha16> in its URL."""
        rows=read_json(self.wp,"media",{"search":identity(sha),"per_page":20,"context":"edit"})
        if not isinstance(rows,list): raise ValueError("Resposta da biblioteca de mídia inválida.")
        found=[r for r in rows if isinstance(r,dict) and has_identity(r.get("source_url"),sha)
               and type(r.get("id")) is int and r["id"]>0]
        if len(found)>1: raise ValueError("Mais de uma mídia com o mesmo hash; reconciliar manualmente.")
        return {"id":found[0]["id"],"source_url":found[0]["source_url"]} if found else None

    def upload(self, path, expected):
        if self.authorization_check: self.authorization_check()
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
        if self.authorization_check: self.authorization_check()
        self.journal.put(key,{"state":"sending"})
        name=upload_name(expected["name"],key,expected.get("role","gallery"))
        try:
            with open(path,"rb") as handle:
                # REST media search matches the title, so the title carries the content identity too.
                response=self.wp.post("media",files={"file":(name,handle,current["mime"])},
                                      data={"title":Path(name).stem}, timeout=httpx.Timeout(self.policy.upload_timeout_seconds,connect=10))
            if response.status_code!=201:
                # Explicit refusal: a later retry may resend, after the library identity check above.
                self.journal.put(key,{"state":"rejected","status":response.status_code})
                raise ValueError(store_refusal(response, current["bytes"]))
            result=response.json()
            if type(result.get("id")) is not int or result["id"]<=0 or not result.get("source_url"):
                raise ValueError("Resposta de upload inválida.")
            media={"id":result["id"],"source_url":result["source_url"]}
            self.journal.put(key,{"state":"done","media":media})
            return {**media,"reused":None}
        except ValueError:
            raise
        except Exception:
            raise ValueError("Upload não confirmado; verificar antes de reprocessar.") from None

    def execute(self, plan, *, audit=lambda event, detail=None: None):
        """Files only: one PUT limited to images and the existing _wcda_arquivos metadata."""
        if self.authorization_check: self.authorization_check()
        dry=plan["dry_run"];approval=plan.get("approval") or {}
        if approval.get("dry_run_sha256")!=dry["dry_run_sha256"]:
            raise ValueError("Dry Run não aprovado ou alterado após a aprovação.")
        if dry["blockers"]:
            raise ValueError("Dry Run com bloqueios; nada enviado.")
        if stale_supplier_datasheet(dry):
            raise ValueError("Dry Run inclui o datasheet do fornecedor; refaça a prévia. Nada enviado.")
        if self.grant:
            grants.check(self.grant,company=self.company,origin=self.woo.credentials.base_url,sku=self.sku,
                         product_id=plan["product_id"],dry_run_sha256=dry["dry_run_sha256"],purpose="publish")
        # Never creates: the exact existing product must still answer for this SKU.
        product=self.woo.find_by_sku(self.sku)
        if not product or product["id"]!=plan["product_id"] or product.get("sku")!=self.sku:
            raise ValueError("Produto/SKU não corresponde à prévia.")
        audit("permissions_verified",self.verify_permissions(product["id"]))
        update_key=grants.update_key(product["id"],dry["dry_run_sha256"])
        previous=self.journal.get(update_key)
        if previous:
            if self.matches(product,previous):
                self.journal.put(update_key,{**previous,"state":"done"})
                return {"status":"done","verified":True,"reconciled":True}
            raise ValueError("Atualização anterior incerta; reconciliar antes de tentar novamente.")
        if snapshot_hash(product)!=plan["snapshot_hash"]:
            raise ValueError("Produto alterado desde a prévia; refaça a prévia.")
        if plan.get("protected_hash") and not protected_matches(product, plan["protected_hash"]):
            raise ValueError("Campos protegidos alterados desde a prévia; nada enviado.")
        # Plan files and Dry Run actions come from the same ordered list; identical bytes may repeat.
        if len(plan["images"])!=len(dry["images"]["actions"]) or len(plan["downloads"])!=len(dry["documents"]["actions"]):
            raise ValueError("Plano de arquivos inconsistente com o Dry Run.")
        # Scoped plans (Cadastro via API): re-validated here, before any upload, never trusted from the UI.
        scope=check_scope(plan)
        images=[i for i,a in zip(plan["images"],dry["images"]["actions"]) if a["action"]=="upload" and a["sha256"]==i["sha256"]]
        documents=[d for d,a in zip(plan["downloads"],dry["documents"]["actions"]) if a["action"]=="add" and a["sha256"]==d["sha256"]]
        uploaded={}
        # Partial failure keeps every confirmed upload in the journal; a retry reuses them.
        for item in images+documents:
            media=self.upload(item["path"],item)
            uploaded[item["sha256"]]=media
            audit("upload_reused" if media["reused"] else "upload_done",{"name":item["name"],"media_id":media["id"]})
        fresh=self.woo.product(product["id"])
        if snapshot_hash(fresh)!=plan["snapshot_hash"] or _protected_hash(fresh)!=_protected_hash(product):
            raise ValueError("Alteração concorrente detectada; mídia enviada preservada para reconciliação.")
        before_wcda=product_snapshot(fresh)["wcda"]
        payload={}
        if scope is not None:
            ids=[i["id"] for i in fresh.get("images",[]) if type(i.get("id")) is int]
            order=scoped_order(ids,dry,scope,images,uploaded)
            if order!=ids:
                payload["images"]=[{"id":i} for i in order]
        elif images:
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
                                                  allow_empty=dry["documents"]["mode"]=="first_inclusion",
                                                  allow_absent=dry["documents"]["mode"]=="absent")
            payload["meta_data"]=document_plan.payload["meta_data"]
        if not payload or not set(payload)<=WRITABLE_KEYS:
            raise ValueError("Payload fora do escopo de arquivos; nada enviado.")
        if scope is not None and (("meta_data" in payload and not scope["documents"])
                                  or ("images" in payload and not (scope["gallery"] or scope["main"]))):
            raise ValueError("Payload fora do escopo aprovado; nada enviado.")
        expected={"images":[i["id"] for i in payload.get("images",fresh.get("images",[]))],
                  "wcda":payload["meta_data"][0]["value"] if documents else before_wcda[0]["value"] if before_wcda else None,
                  "protected":_protected_hash(fresh)}
        # Recovery restores only the two file keys; uploaded media stays in the library.
        rollback={"images":[{"id":i.get("id")} for i in fresh.get("images",[])],
                  "meta_data":[{"id":m.get("id"),"key":m.get("key"),"value":m.get("value")} for m in before_wcda],
                  "media_uploaded":[m["id"] for m in uploaded.values()],"media_deletion":False}
        if documents and not before_wcda:
            rollback["created_wcda"] = True
        if self.authorization_check: self.authorization_check()
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

    def rollback(self, plan, *, audit=lambda event, detail=None: None):
        """Restore only images and _wcda_arquivos captured before the publish. Never deletes media.

        Allowed only when the product is exactly in the expected post-publish state.
        """
        dry=plan["dry_run"]
        if self.authorization_check: self.authorization_check()
        if self.grant:
            grants.check(self.grant,company=self.company,origin=self.woo.credentials.base_url,sku=self.sku,
                         product_id=plan["product_id"],dry_run_sha256=dry["dry_run_sha256"],purpose="rollback")
        key=grants.update_key(plan["product_id"],dry["dry_run_sha256"])
        entry=self.journal.get(key)
        if not entry or "rollback" not in entry: raise ValueError("Não há publicação registrada para recuperar.")
        rollback_key="rollback:"+key
        if (self.journal.get(rollback_key) or {}).get("state")=="done": return {"status":"rolled_back","reconciled":True}
        product=self.woo.product(plan["product_id"])
        if product.get("sku")!=self.sku: raise ValueError("SKU do produto mudou; recuperação recusada.")
        before={"images":[i["id"] for i in entry["rollback"]["images"]],
                "wcda":entry["rollback"]["meta_data"][0]["value"] if entry["rollback"]["meta_data"] else None,
                "protected":entry["protected"]}
        if self.matches(product,before):
            self.journal.put(rollback_key,{"state":"done"})
            return {"status":"nothing_to_restore","verified":True}
        if not self.matches(product,entry):
            raise ValueError("Recuperação bloqueada: estado atual difere do pós-publicação esperado; reconciliar manualmente.")
        audit("permissions_verified",self.verify_permissions(product["id"]))
        payload={"images":entry["rollback"]["images"]}
        metas=entry["rollback"]["meta_data"]
        if entry["rollback"].get("created_wcda"):
            current_meta = product_snapshot(product)["wcda"]
            if len(current_meta) != 1 or type(current_meta[0].get("id")) is not int:
                raise ValueError("Metadado criado não identificado; recuperação bloqueada.")
            metas = [{"id": current_meta[0]["id"], "key": "_wcda_arquivos", "value": []}]
            before["wcda"] = []  # Restore no documents; keep the newly allocated plugin field.
        if metas:
            if len(metas)!=1 or metas[0]["key"]!="_wcda_arquivos" or type(metas[0]["id"]) is not int:
                raise ValueError("Metadado de recuperação inválido.")
            payload["meta_data"]=metas
        if self.authorization_check: self.authorization_check()
        latest = self.woo.product(plan["product_id"])
        if latest.get("sku") != self.sku or not self.matches(latest,entry):
            raise ValueError("Alteração concorrente durante a recuperação; nada enviado.")
        self.journal.put(rollback_key,{"state":"sending"})
        audit("rollback_put_sent",{"keys":sorted(payload)})
        try:
            status=self.woo.client.put(f"products/{product['id']}",json=payload).status_code
        except httpx.RequestError:
            status=None
        verified=self.woo.product(product["id"])
        if status not in {200,None} or not self.matches(verified,before):
            raise ValueError("Recuperação não confirmada pela releitura; reconciliar manualmente.")
        self.journal.put(rollback_key,{"state":"done"})
        audit("rolled_back",{"images":len(before["images"]),"media_kept":entry["rollback"]["media_uploaded"]})
        return {"status":"rolled_back","verified":True,"media_kept":entry["rollback"]["media_uploaded"],"media_deletion":False}

    @staticmethod
    def matches(product, expected):
        wcda=product_snapshot(product)["wcda"]
        return ([i.get("id") for i in product.get("images",[])]==expected["images"]
                and len(wcda) <= 1
                and (wcda[0]["value"] if wcda else None)==expected["wcda"]
                and protected_matches(product,expected["protected"]))


# Metadata that WordPress/plugins rewrite on every product save (observed on the Choice product).
# Never commercial and never part of our payload; any other metadata must stay identical.
VOLATILE_META=("_yoast_indexnow_last_ping","_edit_lock","_edit_last")
VOLATILE_PREFIXES=("_oembed_time_","_oembed_")


def volatile(key):
    return isinstance(key,str) and (key in VOLATILE_META or key.startswith(VOLATILE_PREFIXES))


# Term lists are sets in WooCommerce: the REST API may list them in a different order on each read
# (seen on Portwell: two categories with the same name). Membership is protected, order is not.
UNORDERED_TERMS=("categories","tags","brands")


def _protected_fields(product, *, ordered_terms=False):
    protected={k:v for k,v in _protected(product).items() if k!="images"}
    protected["other_meta_data"]=[m for m in protected["other_meta_data"] if not volatile(m.get("key"))]
    if not ordered_terms:
        for key in UNORDERED_TERMS:
            if isinstance(protected.get(key),list):
                protected[key]=sorted(protected[key],key=lambda t:json.dumps(t,sort_keys=True,ensure_ascii=False))
    return protected


def _protected_hash(product):
    # Every commercial field and every non-volatile metadata must be identical after the file PUT.
    return hashlib.sha256(json.dumps(_protected_fields(product),sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def _legacy_protected_hash(product):
    """Hash stored by versions before 23/10/2026 (term order included); read only for old journals/Dry Runs."""
    return hashlib.sha256(json.dumps(_protected_fields(product,ordered_terms=True),sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def protected_matches(product, stored):
    """A stored protected hash (journal, Dry Run) matches the product under the current or the legacy algorithm."""
    return bool(stored) and stored in {_protected_hash(product),_legacy_protected_hash(product)}


def store_refusal(response, size):
    """Readable reason for a refused media upload. Size limits (413, upload_max_filesize, post_max_size)
    belong to the store's server, not to the PRM, and are named as such; never reported as DNS/network."""
    from app.services.upload_limits import human
    detail = ""
    try:
        body = response.json()
        if isinstance(body, dict):
            detail = " ".join(str(body.get(k) or "") for k in ("code", "message")).strip()
    except ValueError:
        detail = response.text[:300] if response.headers.get("content-type", "").startswith("text/") else ""
    detail = " ".join(re.sub(r"<[^>]+>", " ", detail).split())[:240]
    lowered = detail.lower()
    size_words = ("upload_max_filesize", "post_max_size", "too large", "too big", "file_too_big", "rest_upload_file_too_big",
                  "excede", "tamanho máximo", "request entity too large")
    if response.status_code == 413 or any(w in lowered for w in size_words):
        return (f"A loja recusou o arquivo de {human(size)} por tamanho (HTTP {response.status_code}): o limite do servidor "
                "da loja (WordPress/PHP upload_max_filesize/post_max_size ou proxy) é menor. O PRM aceita até 1 GB, mas não altera "
                "o limite da loja." + (f" Resposta da loja: {detail}." if detail else "") + " Sem retry automático.")
    return (f"A loja recusou o upload (HTTP {response.status_code})." + (f" Resposta da loja: {detail}." if detail else "")
            + " Sem retry automático.")
