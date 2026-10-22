"""Pure file planning for registration: images and WCDA documents only, never commercial fields."""
import re
import unicodedata
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit, unquote

from app.services.registration_files import classify_files, IMAGE_EXTENSIONS, DOCUMENT_EXTENSIONS, DOCUMENT_ROLES

LABELS = {"source_datasheet":"Datasheet", "generated_datasheet":"Datasheet", "manual":"Manual",
          "drawing_3d":"Desenho 3D", "certificate":"Certificado"}


def prepare_files(folder: Path, sku: str, *, company=None):
    classified = classify_files(folder, portable=company is not None, sku=sku, company=company)
    # Original Playwright rules, without its browser operations. A PRM validated
    # manifest remains authoritative; raw folders follow legacy naming semantics.
    if not (folder/"manifest.json").exists():
        photos=folder/"Fotos"
        warnings=list(classified["warnings"])
        if photos.is_dir():
            images=sorted(p for p in photos.iterdir() if p.is_file() and not p.is_symlink()
                          and p.suffix.lower() in {".png",".jpg",".jpeg",".webp"})
            main=None;gallery=[]
            for image in images:
                if re.search(r"front$",image.stem,re.I): gallery.append(str(image))
                else: main=str(image)
            classified.update(main_image=main,gallery=gallery)
            if sum(not re.search(r"front$",p.stem,re.I) for p in images)>1:
                warnings.append("Padrão antigo Fotos/: última imagem não-front é principal; confira antes de confirmar.")
        else:
            images=sorted(p for p in folder.iterdir() if p.is_file() and not p.is_symlink()
                          and p.suffix.lower() in {".png",".jpg",".jpeg",".webp",".svg",".gif"})
            variants=[p for p in images if re.search(r"_variante?$",p.stem,re.I)]
            if len(variants)>1:
                raise ValueError("Mais de uma imagem variante; selecionar a principal antes de importar.")
            numbered=[]
            for p in images:
                if p in variants: continue
                match=re.search(r"(?:_foto_?|[\s_\-])(\d+)$",p.stem,re.I)
                if match: numbered.append((int(match[1]),p))
            numbered.sort(key=lambda item:item[0])
            main=variants[0] if variants else numbered.pop(0)[1] if numbered else None
            classified.update(main_image=str(main) if main else None,gallery=[str(p) for _,p in numbered])
        classified["warnings"]=warnings
    # Keep legacy primary ordering, but never silently drop other uploaded assets.
    selected=([classified["main_image"]] if classified["main_image"] else [])+classified["gallery"]
    known={d["path"] for d in classified["documents"]}
    manifest=(folder/"manifest.json").is_file()
    taken={str(Path(p).resolve()) for p in [*selected,*known]}
    sources=[]
    for path in sorted(folder.rglob("*")):
        if not path.is_file() or path.is_symlink(): continue
        if path.suffix.lower() not in IMAGE_EXTENSIONS|DOCUMENT_EXTENSIONS or str(path.resolve()) in taken: continue
        # A validated PRM manifest is authoritative: undeclared assets are rejected, not published.
        if manifest:
            raise ValueError("Arquivo não declarado no manifesto PRM: "+path.relative_to(folder).as_posix()+".")
        # Batch exports keep raw supplier sources in fontes/: inventory only, never upload automatically.
        if any(p.casefold()=="fontes" for p in path.relative_to(folder).parts[:-1]):
            sources.append({"name":path.name,"bytes":path.stat().st_size})
            continue
        if path.suffix.lower() in IMAGE_EXTENSIONS:
            selected.append(str(path))
        else:
            role=next((r for r,p in DOCUMENT_ROLES if p.search(path.stem)),"other")
            classified["documents"].append({"role":role,"path":str(path)})
    if sources:
        classified["warnings"].append(f"{len(sources)} fonte(s) do lote em fontes/ apenas inventariada(s); não entram no cadastro.")
    if not classified["main_image"] and selected:
        classified["warnings"].append("Principal sem padrão legado; primeira imagem na prévia, revisar ordem antes de publicar.")
    classified["main_image"]=selected[0] if selected else None
    classified["gallery"]=selected[1:]
    documents = classified["documents"]
    counts = Counter(item["role"] for item in documents)
    # When the package declares the PRM datasheet, the supplier original (older exports) is excluded:
    # only the generated datasheet is published.
    generated = "generated_datasheet" in counts
    excluded = [d for d in documents if generated and d["role"] == "source_datasheet"]
    documents = [d for d in documents if d not in excluded]
    counts = Counter(item["role"] for item in documents)
    labels = LABELS
    roles = ["generated_datasheet", "source_datasheet", *[r for r in LABELS if "datasheet" not in r]]
    ordered = sorted(documents, key=lambda item: (
        roles.index(item["role"]) if item["role"] in roles else len(roles),
        Path(item["path"]).name.casefold()))
    seen, downloads = {}, []
    for item in ordered:
        description = re.sub(rf"^{re.escape(sku)}[\s_\-]*", "", Path(item["path"]).stem, flags=re.I).strip(" _-")
        label = labels[item["role"]] if item["role"] in labels and counts[item["role"]] == 1 else description or Path(item["path"]).stem
        seen[label] = seen.get(label, 0) + 1
        downloads.append({**item, "label":label if seen[label] == 1 else f"{label} ({seen[label]})"})
    return {"main_image":classified["main_image"], "gallery":classified["gallery"], "downloads":downloads,
            "excluded":[{"name":Path(d["path"]).name,"role":d["role"]} for d in excluded],
            "sources":sources, "warnings":classified["warnings"], "read_only":True,
            "wcda_mapping":"candidate_contract_append"}


# Commercial data belongs to the CSV flow. This plan may only touch these product keys.
WRITABLE_KEYS = {"images", "meta_data"}
PROTECTED_FIELDS = ["name", "description", "short_description", "categories", "attributes", "sku",
                    "regular_price", "sale_price", "stock_quantity", "stock_status", "status", "demais meta_data"]


def stale_supplier_datasheet(dry):
    """Dry Runs prepared before the rule may still add the supplier datasheet: never execute them."""
    actions = (dry or {}).get("documents", {}).get("actions", [])
    return any(a["role"] == "source_datasheet" and a["action"] == "add" for a in actions) and \
        any(a["role"] == "generated_datasheet" for a in actions)


def identity(sha):
    """Content identity embedded in every PRM upload name; survives WordPress suffixes (-1, -scaled)."""
    return "prm-" + sha[:16]


def upload_name(name, sha, role):
    path = Path(name)
    if role in {"main_image", "gallery"}:
        return "prm-" + sha + path.suffix.lower()
    stem = unicodedata.normalize("NFKD", path.stem).encode("ascii", "ignore").decode()
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-.") or "documento"
    return f"{stem[:80]}_{identity(sha)}{path.suffix.lower()}"


def has_identity(value, sha):
    return isinstance(value, str) and identity(sha) in unquote(value).casefold()


def format_filesize(size):
    """Observed WCDA format (`421.1 KB`, `1.09 MB`); plugin recognition still requires verification."""
    if size < 1024: return f"{size} B"
    if size < 1024**2: return f"{round(size/1024, 1):g} KB"
    if size < 1024**3: return f"{round(size/1024**2, 2):g} MB"
    return f"{round(size/1024**3, 2):g} GB"


def wcda_state(product):
    from app.services.store_document_update import metadata_field
    try:
        field = metadata_field(product)
        return {"mode": "append", "meta_id": field["id"], "entries": field["value"]}
    except ValueError as first:
        try:
            field = metadata_field(product, allow_empty=True)
            return {"mode": "first_inclusion", "meta_id": field["id"], "entries": []}
        except ValueError as exc:
            return {"mode": "blocked", "meta_id": None, "entries": [], "reason": str(exc if "lista" in str(exc) else first)}


def file_plan(product, images, documents):
    """Dry Run of files only: what is added, preserved or ignored. No IDs or URLs are invented."""
    existing = [{"id": i.get("id"), "name": Path(unquote(urlsplit(i.get("src") or "").path)).name}
                for i in product.get("images", [])]
    names = {e["name"].casefold() for e in existing if e["name"]}
    image_actions, seen = [], set()
    for item in images:
        if item["sha256"] in seen: action = "duplicate_in_package"
        elif any(has_identity(e["name"], item["sha256"]) for e in existing): action = "already_linked"
        elif item["name"].casefold() in names: action = "conflict"
        else: action = "upload"
        seen.add(item["sha256"])
        image_actions.append({"name": item["name"], "role": item["role"], "bytes": item["bytes"], "sha256": item["sha256"],
                              "upload_name": upload_name(item["name"], item["sha256"], item["role"]), "action": action})
    uploads = [i for i in image_actions if i["action"] == "upload"]
    new_main = next((i for i in uploads if i["role"] == "main_image"), None)
    current = [{"source": "existing", "id": e["id"], "name": e["name"]} for e in existing]
    added = [{"source": "upload", "id": None, "name": i["name"], "status": "pending_upload"} for i in uploads]
    replaced = ([added[uploads.index(new_main)]] + current + [a for a in added if a["name"] != new_main["name"]]) if existing and new_main else None
    wcda = wcda_state(product)
    entries = wcda["entries"]
    document_actions = []
    for item in documents:
        filename = upload_name(item["name"], item["sha256"], item["role"])
        if item["sha256"] in seen: action = "duplicate_in_package"
        elif any(has_identity(e.get("url"), item["sha256"]) or has_identity(e.get("filename"), item["sha256"]) for e in entries):
            action = "already_linked"
        elif any(isinstance(e.get(k), str) and e[k].casefold() == v.casefold() for e in entries
                 for k, v in (("label", item["label"]), ("filename", filename), ("filename", item["name"]))):
            action = "conflict"
        else:
            action = "add"
        seen.add(item["sha256"])
        document_actions.append({"label": item["label"], "name": item["name"], "role": item["role"], "bytes": item["bytes"],
                                 "sha256": item["sha256"], "upload_name": filename, "action": action,
                                 "wcda_entry": {"label": item["label"], "filename": filename, "filesize": format_filesize(item["bytes"]),
                                                "url": None} if action == "add" else None})
    adding = [d for d in document_actions if d["action"] == "add"]
    blockers = []
    if any(i["action"] == "conflict" for i in image_actions):
        blockers.append("Imagem com mesmo nome já vinculada sem identidade PRM; conteúdo não comprovado. Reconciliar para evitar duplicata.")
    if any(d["action"] == "conflict" for d in document_actions):
        blockers.append("Documento com mesmo label/arquivo já no WCDA em outra URL; reconciliar antes de incluir.")
    if adding and wcda["mode"] == "blocked":
        blockers.append("_wcda_arquivos incompatível: " + wcda["reason"])
    if not uploads and not adding and not blockers:
        blockers.append("Nada a enviar: imagens e documentos já vinculados.")
    return {
        "scope": "files_only", "writable_keys": sorted(WRITABLE_KEYS), "protected_fields": PROTECTED_FIELDS,
        "images": {"current": existing, "actions": image_actions, "final_order": current + added,
                   "main_image": {"current": existing[0] if existing else None,
                                  "proposed": (current + added)[0] if current + added else None,
                                  "action": "preserve" if existing else "set_from_upload" if uploads else "none",
                                  "replacement_available": replaced is not None,
                                  "replacement_order": replaced,
                                  "replacement_requires": "aprovação explícita replace_main" if replaced else None}},
        "documents": {"mode": wcda["mode"], "meta_id": wcda["meta_id"], "reason": wcda.get("reason"),
                      "existing": [{"position": n, "label": e.get("label"), "filename": e.get("filename"),
                                    "filesize": e.get("filesize")} for n, e in enumerate(entries)],
                      "actions": document_actions, "preserve_existing_order": True,
                      "final_count": len(entries) + len(adding)},
        "rollback": {"images_before": [e["id"] for e in existing], "wcda_meta_id": wcda["meta_id"],
                     "wcda_before_count": len(entries),
                     "strategy": "PUT restaurando somente images e _wcda_arquivos anteriores, após confirmar que o estado atual é o pós-publicação esperado.",
                     "media_deletion": False},
        "blockers": blockers,
        "dependencies": (["IDs de mídia e URLs reais só existem após upload autorizado; nenhum valor fictício é usado."] if uploads or adding else []) +
                        (["Primeira inclusão em _wcda_arquivos vazio; rollback restaura lista vazia. Reconhecimento do plugin a verificar no frontend."] if adding and wcda["mode"] == "first_inclusion" else []),
    }
