"""Durable review/approve/confirm queue for product files (images, WCDA); no browser automation."""
import csv
import hashlib
import io
import json
import shutil
import sqlite3
import stat
import time
import uuid
import zipfile
from pathlib import Path
from contextlib import contextmanager

from openpyxl import load_workbook
from app.services.store_config import ROOT, COMPANIES, StoreSettings
from app.services.store_publish import MIMES, PublishSettings, StagingPublisher, file_info, snapshot_hash
from app.services.store_registration_plan import prepare_files, file_plan
from app.services.registration_files import find_product_folder
from app.services.registration_woo_api import WooClient, credentials_for
from app.services.datasheet_batches import relative_name, identify_product_folders
from app.services.digitalization_storage import validate_sku
from app.services.store_documents import interpret_documents


def parse_skus(raw, name, *, details=False, strict=False):
    if len(raw)>5*1024**2:
        raise ValueError("Planilha acima de 5 MiB.")
    if name.lower().endswith(".csv"):
        try: text=raw.decode("utf-8-sig")
        except UnicodeError: text=raw.decode("cp1252")
        try: dialect=csv.Sniffer().sniff(text[:2000],delimiters=",;\t")
        except csv.Error: dialect=csv.excel
        rows=list(csv.reader(io.StringIO(text),dialect))
    elif name.lower().endswith((".xlsx",".xlsm")):
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            if sum(i.file_size for i in archive.infolist())>30*1024**2:
                raise ValueError("Planilha descompactada excessiva.")
        book=load_workbook(io.BytesIO(raw),read_only=True,data_only=True)
        try:
            rows=[]
            for row in book.active.iter_rows(values_only=True):
                if len(rows)>1000: raise ValueError("Limite de 1000 linhas.")
                rows.append(["" if v is None else str(int(v)) if isinstance(v,float) and v.is_integer() else str(v) for v in row])
        finally: book.close()
    else: raise ValueError("Envie CSV ou XLSX/XLSM.")
    rows=[r for r in rows if any(str(v).strip() for v in r)]
    if not rows or len(rows)>1000: raise ValueError("Planilha vazia ou acima de 1000 linhas.")
    headers=[v.strip().lower() for v in rows[0]]
    aliases={"sku","código","codigo","cod","cod.","código cigam","codigo cigam"}
    index=next((i for i,h in enumerate(headers) if h in aliases),None)
    if index is None:
        if any(len(r)!=1 for r in rows): raise ValueError("Informe uma coluna SKU/CIGAM.")
        index=0
    else: rows=rows[1:]
    skus=[]; records={}
    for row in rows:
        if index>=len(row) or not row[index].strip(): continue
        sku=validate_sku(row[index] if strict else row[index].strip())
        if "e+" in sku.lower(): raise ValueError("SKU em notação científica; envie como texto.")
        if strict and sku in records: raise ValueError("SKU duplicado na planilha complementar.")
        if sku not in skus: skus.append(sku)
        record={h:row[i] for i,h in enumerate(headers) if i<len(row) and h in
                {"nome","descricao","descricao_curta","categoria","empresa","observacoes"}}
        if sku in records and records[sku]!=record: raise ValueError("Linhas conflitantes para o mesmo SKU.")
        records[sku]=record
    if not skus: raise ValueError("Nenhum SKU.")
    return records if details else skus


BATCH_REPORTS={"relatorio_processamento.csv","erros.csv"}


def batch_bundle(entries, directories, company):
    """Recognize the Geração em Lote export: COMPANY/SKU.pdf, COMPANY/SKU/analysis.json, COMPANY/SKU/fontes/.

    Returns entries renamed to one folder per SKU, or None for any other layout.
    """
    names=[n for n,_ in entries]
    reports={n for n in names if "/" not in n and n.lower().endswith(".csv")}
    tops={n.split("/")[0] for n in names if "/" in n}|{d.split("/")[0] for d in directories}
    if not reports or not reports<=BATCH_REPORTS or len(tops)!=1 or next(iter(tops)) not in {c.upper() for c in COMPANIES}:
        return None
    if next(iter(tops))!=company.upper(): raise ValueError("Pacote do lote pertence a outra empresa.")
    renamed=[]
    for name,info in entries:
        if name in reports: continue
        parts=name.split("/")
        if len(parts)==2 and parts[1].lower().endswith(".pdf"):
            sku=validate_sku(parts[1][:-4]);name=f"{parts[0]}/{sku}/{sku}_Datasheet.pdf"
        renamed.append((name,info))
    if len({n.casefold() for n,_ in renamed})!=len(renamed): raise ValueError("Caminho duplicado.")
    return renamed


def extract_files(raw, target, *, identification="csv", archive_name="", root="", company=""):
    if len(raw)>100*1024**2: raise ValueError("ZIP acima de 100 MiB.")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos=archive.infolist()
        if len(infos)>3000 or sum(i.file_size for i in infos)>500*1024**2:
            raise ValueError("ZIP excede limites.")
        names=set(); entries=[]; directories=[]
        for info in infos:
            name=relative_name(info.orig_filename)
            if name.casefold() in names: raise ValueError("Caminho duplicado.")
            names.add(name.casefold())
            mode=info.external_attr>>16
            if stat.S_ISLNK(mode) or stat.S_IFMT(mode) not in {0,stat.S_IFREG,stat.S_IFDIR} or info.flag_bits&1:
                raise ValueError("Link ou criptografia não permitidos.")
            if info.is_dir():
                directories.append(name)
                continue
            if info.file_size>20*1024**2 or info.file_size/max(1,info.compress_size)>200:
                raise ValueError("Arquivo excessivo ou compressão suspeita.")
            suffix=Path(name).suffix.lower()
            if suffix not in {".png",".jpg",".jpeg",".webp",".pdf",".zip",".step",".stp",".dwg",".dxf",".rar",".7z",".svg",".gif",".json",".csv"}:
                raise ValueError("Extensão não permitida.")
            if suffix==".json" and Path(name).name not in {"manifest.json","datasheet_dados.json","analysis.json","product.json"}:
                raise ValueError("JSON não reconhecido; envie apenas dados/manifesto do produto.")
            if suffix in {".json",".csv"} and info.file_size>5*1024**2:
                raise ValueError("Metadados/planilha acima de 5 MiB.")
            entries.append((name,info))
        bundle=batch_bundle(entries,directories,company) if identification=="folder" and not root else None
        if bundle is not None:
            entries=bundle;root=entries[0][0].split("/")[0] if entries else ""
            directories=[d for d in directories if d.split("/")[0]==root]
        prefixes=identify_product_folders([n for n,_ in entries],directories,root,archive_name=archive_name) if identification=="folder" else {}
        if identification=="folder":
            if not prefixes or len(prefixes)>1000: raise ValueError("Nenhum SKU identificado ou limite de 1000 excedido.")
            if len({s.casefold() for s in prefixes})!=len(prefixes): raise ValueError("SKUs duplicados no ZIP.")
            for sku in prefixes:
                validate_sku(sku)
                (target/sku).mkdir(parents=True,exist_ok=True)
        csvs=[(n,i) for n,i in entries if n.lower().endswith('.csv')]
        if len(csvs)>1: raise ValueError("Envie no máximo um CSV complementar no ZIP.")
        for name,info in entries:
            if name.lower().endswith('.csv'): continue
            destination=name
            if prefixes:
                matches=[s for s,prefix in prefixes.items() if name.startswith(prefix)]
                if len(matches)!=1: raise ValueError("Arquivo sem pasta de SKU inequívoca.")
                sku=matches[0];destination=sku+"/"+name[len(prefixes[sku]):]
            path=(target/destination).resolve()
            if not path.is_relative_to(target.resolve()): raise ValueError("Caminho inválido.")
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(archive.read(info))
        return list(prefixes), (archive.read(csvs[0][1]),csvs[0][0]) if csvs else None


class Jobs:
    def __init__(self, policy=None):
        self.policy=policy or PublishSettings()
        self.root=Path(self.policy.storage_dir)
        if not self.root.is_absolute(): self.root=ROOT/self.root
        self.root=self.root.resolve();self.root.mkdir(parents=True,exist_ok=True)
        with self.db() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS batches(id TEXT PRIMARY KEY,org TEXT,owner TEXT,company TEXT,origin TEXT,created REAL);
            CREATE TABLE IF NOT EXISTS jobs(batch TEXT,sku TEXT,state TEXT,error TEXT DEFAULT '',plan TEXT DEFAULT '{}',
              token TEXT DEFAULT '',lease REAL DEFAULT 0,PRIMARY KEY(batch,sku));
            CREATE TABLE IF NOT EXISTS journal(scope TEXT,key TEXT,value TEXT,PRIMARY KEY(scope,key));
            CREATE TABLE IF NOT EXISTS audit(batch TEXT,sku TEXT,at REAL,actor TEXT,event TEXT,detail TEXT);
            """)

    @contextmanager
    def db(self):
        db=sqlite3.connect(self.root/"jobs.sqlite3",timeout=20)
        db.row_factory=sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self, company, org, owner, skus, archive, settings, *, identification="csv", archive_name="", root="", complements=None):
        if company not in COMPANIES: raise ValueError("Empresa inválida.")
        if identification not in {"csv","folder"}: raise ValueError("Modo de identificação inválido.")
        if identification=="csv" and not skus: raise ValueError("Selecione a planilha no modo CSV ou utilize nome da pasta.")
        origin=settings.credentials(company,"wc").base_url
        identifier=uuid.uuid4().hex; folder=self.root/identifier
        folder.mkdir()
        try:
            found,embedded=extract_files(archive,folder,identification=identification,archive_name=archive_name,root=root,company=company)
            if embedded:
                if complements is not None: raise ValueError("Use uma única planilha complementar: externa ou dentro do ZIP.")
                complements=parse_skus(*embedded,details=True,strict=True)
            if identification=="folder":
                if skus and any(s not in found for s in skus): raise ValueError("SKU da planilha não corresponde exatamente ao nome da pasta/ZIP.")
                skus=found
            complements=complements or {}
            if any(s not in skus for s in complements): raise ValueError("Planilha contém SKU sem pasta correspondente.")
            if any(r.get("empresa", "").strip() and r["empresa"].strip().lower()!=company for r in complements.values()):
                raise ValueError("Empresa da planilha diverge da loja selecionada.")
        except BaseException:
            # Rejected intake leaves no orphan extraction; the folder is new and owned by this call.
            shutil.rmtree(folder,ignore_errors=True)
            raise
        with self.db() as db:
            db.execute("INSERT INTO batches VALUES(?,?,?,?,?,?)",(identifier,str(org),str(owner),company,origin,time.time()))
            db.executemany("INSERT INTO jobs(batch,sku,state,plan) VALUES(?,?,'preview_queued',?)",
                [(identifier,s,json.dumps({"input":{"identification":identification,"complement":complements.get(s,{})}})) for s in skus])
        return identifier

    def access(self, db, identifier, org, owner):
        row=db.execute("SELECT * FROM batches WHERE id=? AND org=? AND owner=?",(identifier,str(org),str(owner))).fetchone()
        if not row: raise LookupError("Lote não encontrado.")
        return row

    def audit(self, batch, sku, actor, event, detail=None, db=None):
        """Append-only audit trail; never stores paths, credentials or HTTP bodies."""
        row=(batch,sku,time.time(),str(actor),event,json.dumps(detail or {},ensure_ascii=False))
        if db is not None: db.execute("INSERT INTO audit VALUES(?,?,?,?,?,?)",row)
        else:
            with self.db() as conn: conn.execute("INSERT INTO audit VALUES(?,?,?,?,?,?)",row)

    def detail(self, identifier, org, owner):
        with self.db() as db:
            batch=dict(self.access(db,identifier,org,owner))
            items=[]
            for row in db.execute("SELECT * FROM jobs WHERE batch=?",(identifier,)).fetchall():
                plan=json.loads(row["plan"])
                dry=plan.get("dry_run")
                # No local paths, remote metadata or source URLs in frontend.
                items.append({"sku":row["sku"],"state":row["state"],"error":row["error"],
                    "files":[{"name":i["name"],"bytes":i["bytes"],"role":i.get("role","image"),"label":i.get("label","")}
                             for i in plan.get("images",[])+plan.get("downloads",[])]+
                            [{"name":i["name"],"bytes":i["bytes"],"role":"source","label":"fonte (não publicada)"} for i in plan.get("sources",[])],
                    "existing_images":plan.get("existing_images"),"existing_documents":plan.get("existing_documents"),
                    "product_id":plan.get("product_id"),"dry_run":dry,
                    "blockers":(dry or {}).get("blockers",[]),"approval":plan.get("approval"),
                    "result":plan.get("result"),
                    "audit":[{"at":a["at"],"actor":a["actor"],"event":a["event"],"detail":json.loads(a["detail"])} for a in
                             db.execute("SELECT * FROM audit WHERE batch=? AND sku=? ORDER BY at",(identifier,row["sku"]))],
                    "preparation_status":"prepared" if plan.get("product_id") else "pending",
                    "warnings":plan.get("warnings",[])})
        ready=[i for i in items if i["state"]=="review" and approved(i)]
        try:
            for item in ready: self.policy.authorize(batch["origin"],item["sku"])
            can_confirm=bool(ready)
        except ValueError:
            can_confirm=False
        return {"id":identifier,"company":batch["company"],"created":batch["created"],"items":items,"can_confirm":can_confirm}

    def history(self,org,owner):
        with self.db() as db:
            return [dict(r) for r in db.execute("SELECT id,company,created FROM batches WHERE org=? AND owner=? ORDER BY created DESC LIMIT 100",(str(org),str(owner)))]

    def approve(self, identifier, org, owner, skus=None, replace_main=()):
        """Individual (skus) or batch approval of the exact Dry Run. Never queues or authorizes a write.

        Replacing an existing main image requires naming the SKU in replace_main.
        """
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            self.access(db,identifier,org,owner)
            rows=[r for r in db.execute("SELECT * FROM jobs WHERE batch=? AND state='review'",(identifier,)).fetchall()
                  if skus is None or r["sku"] in skus]
            if skus is not None and len(rows)!=len(set(skus)): raise ValueError("SKU fora do lote ou sem Dry Run apto.")
            approved_skus=[]
            for row in rows:
                plan=json.loads(row["plan"])
                main=plan["dry_run"]["images"]["main_image"]
                replace=row["sku"] in replace_main
                if replace and not main["replacement_available"]: raise ValueError("Substituição de principal indisponível para "+row["sku"]+".")
                plan["approval"]={"by":str(owner),"at":time.time(),"dry_run_sha256":plan["dry_run"]["dry_run_sha256"],
                                  "replace_main":replace,"writes_authorized":False}
                db.execute("UPDATE jobs SET plan=? WHERE batch=? AND sku=? AND state='review'",(json.dumps(plan),identifier,row["sku"]))
                self.audit(identifier,row["sku"],owner,"approved",{"dry_run_sha256":plan["approval"]["dry_run_sha256"],"replace_main":replace},db)
                approved_skus.append(row["sku"])
            if not approved_skus: raise ValueError("Nenhum Dry Run pronto para aprovação.")
            return approved_skus

    def confirm(self, identifier, org, owner, settings):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            batch=self.access(db,identifier,org,owner)
            if settings.credentials(batch["company"],"wc").base_url!=batch["origin"]:
                raise ValueError("Destino alterado; importe um novo lote.")
            rows=[r for r in db.execute("SELECT * FROM jobs WHERE batch=? AND state='review'",(identifier,)).fetchall()
                  if approved({"approval":json.loads(r["plan"]).get("approval"),"dry_run":json.loads(r["plan"]).get("dry_run")})]
            if not rows: raise ValueError("Nenhum item aprovado apto.")
            for row in rows:
                self.policy.authorize(batch["origin"],row["sku"])
            for row in rows:
                db.execute("UPDATE jobs SET state='queued' WHERE batch=? AND sku=? AND state='review'",(identifier,row["sku"]))
                self.audit(identifier,row["sku"],owner,"queued",{"origin":batch["origin"]},db)

    def reprocess(self, identifier, org, owner):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            self.access(db,identifier,org,owner)
            # Rebuild preview only. Uncertain writes never automatically re-upload.
            db.execute("UPDATE jobs SET state='preview_queued',error='' WHERE batch=? AND state='error'",(identifier,))

    def claim(self):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE jobs SET state='uncertain',error='Worker interrompido; reconciliar manualmente.',token='' WHERE state IN ('preview_running','running') AND lease<?",(time.time(),))
            if db.execute("SELECT 1 FROM jobs WHERE state IN ('preview_running','running')").fetchone(): return None
            row=db.execute("SELECT j.*,b.company,b.origin,b.org FROM jobs j JOIN batches b ON b.id=j.batch WHERE state IN ('preview_queued','queued') ORDER BY b.created LIMIT 1").fetchone()
            if not row: return None
            job=dict(row);job["token"]=uuid.uuid4().hex
            db.execute("UPDATE jobs SET state=?,token=?,lease=? WHERE batch=? AND sku=?",
                ("preview_running" if job["state"]=="preview_queued" else "running",job["token"],time.time()+3600,job["batch"],job["sku"]))
            return job

    def finish(self, job, state, plan=None, error=""):
        with self.db() as db:
            db.execute("UPDATE jobs SET state=?,plan=?,error=?,token='' WHERE batch=? AND sku=? AND token=?",
                (state,json.dumps(plan or json.loads(job["plan"])),error,job["batch"],job["sku"],job["token"]))


def approved(item):
    approval,dry=item.get("approval"),item.get("dry_run") or {}
    return bool(approval) and approval.get("dry_run_sha256")==dry.get("dry_run_sha256")


class Journal:
    def __init__(self,jobs,scope): self.jobs,self.scope=jobs,scope
    def get(self,key):
        with self.jobs.db() as db:
            row=db.execute("SELECT value FROM journal WHERE scope=? AND key=?",(self.scope,key)).fetchone()
            return json.loads(row[0]) if row else None
    def put(self,key,value):
        with self.jobs.db() as db:
            db.execute("INSERT OR REPLACE INTO journal VALUES(?,?,?)",(self.scope,key,json.dumps(value)))


def process_one(jobs, settings, transport=None):
    job=jobs.claim()
    if not job: return False
    woo=None;publisher=None
    try:
        if settings.organization_id!=job["org"]:
            raise ValueError("Organização não corresponde à configuração.")
        if settings.credentials(job["company"],"wc").base_url!=job["origin"]:
            raise ValueError("Destino mudou; importe novo lote.")
        if job["state"]=="preview_queued":
            inputs=json.loads(job["plan"]).get("input",{})
            folder=find_product_folder(jobs.root/job["batch"],job["sku"])
            if not folder: raise ValueError("Pasta exata do SKU não encontrada no ZIP.")
            if folder.name!=job['sku']: raise ValueError("Nome da pasta não corresponde exatamente ao SKU.")
            files=prepare_files(folder,job["sku"],company=job["company"])
            selected=([files["main_image"]] if files["main_image"] else [])+files["gallery"]
            images=[{"path":str(p),"role":"main_image" if n==0 else "gallery",**file_info(p,jobs.policy.max_file_mib)}
                    for n,p in enumerate(selected)]
            if len(images)>20: raise ValueError("Limite de 20 imagens por produto.")
            # Formats not homologated for upload (e.g. .step/.dwg/.rar) are reported and ignored, never sent.
            unsupported=[d for d in files["downloads"] if Path(d["path"]).suffix.lower() not in MIMES]
            documents=[{**d,**file_info(d["path"],jobs.policy.max_file_mib)} for d in files["downloads"] if d not in unsupported]
            if not images and not documents: raise ValueError("Nenhum arquivo reconhecido.")
            woo=WooClient(credentials_for(job["company"],settings),transport=transport)
            product=woo.find_by_sku(job["sku"])
            if not product: raise ValueError("SKU não existe na loja; criação automática proibida.")
            product=woo.product(product["id"])
            if product.get('sku')!=job['sku']: raise ValueError("SKU mudou durante a consulta; refaça a prévia.")
            # Private immutable backup for this preview attempt. No remote write is performed.
            backup=jobs.root/'_snapshots'/job['batch']
            backup.mkdir(parents=True,exist_ok=True)
            snapshot=json.dumps({"company":job['company'],"origin":job['origin'],"sku":job['sku'],"product":product},ensure_ascii=False)
            with (backup/(job['token']+'.json')).open('x',encoding='utf-8') as handle: handle.write(snapshot)
            dry={"dry_run":True,"writes_allowed":False,"product_id":product["id"],"sku":job["sku"],
                 **file_plan(product,images,documents),"backup_sha256":hashlib.sha256(snapshot.encode('utf-8')).hexdigest(),
                 "ignored":[{"name":Path(d["path"]).name,"label":d["label"],"reason":"Formato sem upload homologado."} for d in unsupported]}
            try: jobs.policy.authorize(job['origin'],job['sku'])
            except ValueError as exc: dry["write_gate"]="Política de gravação: "+str(exc)
            else: dry["write_gate"]="Staging autorizado para este SKU; execução exige aprovação e confirmação."
            dry['dry_run_sha256']=hashlib.sha256(json.dumps(dry,sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest()
            current_documents=interpret_documents(product)
            plan={"input":{"identification":inputs.get("identification")},"product_id":product["id"],"snapshot_hash":snapshot_hash(product),
                  "images":images,"downloads":documents,"sources":files.get("sources",[]),
                  "existing_images":len(product.get("images",[])),
                  "existing_documents":len(current_documents["documents"]),
                  "dry_run":dry,
                  "warnings":files["warnings"]+current_documents["warnings"]}
            state="blocked" if dry["blockers"] else "review"
            jobs.finish(job,state,plan,"; ".join(dry["blockers"]) if dry["blockers"] else "")
            jobs.audit(job["batch"],job["sku"],"worker","preview_"+state,{"dry_run_sha256":dry["dry_run_sha256"]})
        else:
            plan=json.loads(job["plan"])
            journal=Journal(jobs,job["org"]+"|"+job["origin"]+"|"+job["sku"])
            publisher=StagingPublisher(job["company"],job["sku"],settings,jobs.policy,journal,transport=transport)
            result=publisher.execute(plan,audit=lambda event,detail=None:jobs.audit(job["batch"],job["sku"],"worker",event,detail))
            jobs.finish(job,"done",{**plan,"result":result})
            jobs.audit(job["batch"],job["sku"],"worker","done",{"verified":result.get("verified")})
    except Exception as exc:
        # HTTP bodies and local filesystem paths must not leak to reports.
        error=str(exc) if type(exc) is ValueError and len(str(exc))<240 else "Falha "+type(exc).__name__+"; confira configuração e arquivos."
        jobs.finish(job,"error",error=error)
        jobs.audit(job["batch"],job["sku"],"worker","error",{"error":error})
    finally:
        if woo: woo.close()
        if publisher: publisher.close()
    return True
