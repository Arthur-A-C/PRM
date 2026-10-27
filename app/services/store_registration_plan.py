"""Pure file planning for registration: images and WCDA documents only, never commercial fields."""
import hashlib
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit, unquote

from app.services.registration_files import classify_files, IMAGE_EXTENSIONS, DOCUMENT_EXTENSIONS, DOCUMENT_ROLES

LABELS = {"source_datasheet":"Datasheet", "generated_datasheet":"Datasheet", "manual":"Manual",
          "drawing_3d":"Desenho 3D", "certificate":"Certificado"}


def prepare_files(folder: Path, sku: str, *, company=None, numbered=False):
    """numbered=True (Cadastro via API with scope): raw folders are classified later by <SKU>_<n>.ext only,
    so no legacy main/gallery guess is made here; every supported image is just listed."""
    classified = classify_files(folder, portable=company is not None, sku=sku, company=company)
    # Original Playwright rules, without its browser operations. A PRM validated
    # manifest remains authoritative; raw folders follow legacy naming semantics.
    if numbered and not (folder/"manifest.json").exists():
        classified.update(main_image=None, gallery=[])
    elif not (folder/"manifest.json").exists():
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
    sources,unsupported_images=[],[]
    for path in sorted(folder.rglob("*")):
        if not path.is_file() or path.is_symlink(): continue
        if numbered and not manifest and path.suffix.lower() in UNSUPPORTED_IMAGE_EXTENSIONS                 and not any(p.casefold()=="fontes" for p in path.relative_to(folder).parts[:-1]):
            unsupported_images.append({"name":path.name,"bytes":path.stat().st_size})
            continue
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
    # Whether the first image is the main by the folder/manifest pattern, or only by position.
    main_from_pattern=bool(classified["main_image"])
    if not classified["main_image"] and selected and not (numbered and not manifest):
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
            "main_from_pattern":main_from_pattern and bool(selected), "manifest":manifest,
            "unsupported_images":unsupported_images,
            "excluded":[{"name":Path(d["path"]).name,"role":d["role"]} for d in excluded],
            "sources":sources, "warnings":classified["warnings"], "read_only":True,
            "wcda_mapping":"candidate_contract_append"}


# Image formats the upload pipeline does not homologate (no conversion here; see Resolução de Imagens).
UNSUPPORTED_IMAGE_EXTENSIONS = {".svg", ".gif"}


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
    metadata = product.get("meta_data")
    if isinstance(metadata, list) and all(isinstance(m, dict) for m in metadata) and not any(m.get("key") == "_wcda_arquivos" for m in metadata):
        return {"mode": "absent", "meta_id": None, "entries": [],
                "reason": "_wcda_arquivos ausente — será criado automaticamente."}
    try:
        field = metadata_field(product)
        return {"mode": "append", "meta_id": field["id"], "entries": field["value"]}
    except ValueError as first:
        try:
            field = metadata_field(product, allow_empty=True)
            return {"mode": "first_inclusion", "meta_id": field["id"], "entries": []}
        except ValueError as exc:
            return {"mode": "blocked", "meta_id": None, "entries": [], "reason": str(exc if "lista" in str(exc) else first)}


def store_limit_check(dry, limit):
    """PRM accepts up to 1 GB per file, the store may accept less: files the store would refuse block the Dry Run.
    Returns warnings for the item (shown with the plan warnings)."""
    from app.services.upload_limits import human
    dry["store_upload_limit"] = limit
    sending = [a for a in dry["images"]["actions"] if a["action"] == "upload"] +               [a for a in dry["documents"]["actions"] if a["action"] == "add"]
    if limit is None:
        return ["A loja não informou pela API o limite de upload (WordPress/PHP). Arquivos grandes podem ser recusados por ela; "
                "o erro real será mostrado."] if sending else []
    for action in sending:
        if action["bytes"] > limit:
            dry["blockers"].append(f"{action.get('label') or action['name']} tem {human(action['bytes'])}, acima do limite de upload "
                                   f"da loja ({human(limit)}). O PRM aceita até 1 GB por arquivo, mas a loja recusaria este envio; "
                                   "reduza o arquivo ou peça o aumento do limite na loja.")
    return []


def _document_actions(documents, entries, seen):
    actions = []
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
        actions.append({"label": item["label"], "name": item["name"], "role": item["role"], "bytes": item["bytes"],
                        "sha256": item["sha256"], "upload_name": filename, "action": action,
                        "wcda_entry": {"label": item["label"], "filename": filename, "filesize": format_filesize(item["bytes"]),
                                       "url": None} if action == "add" else None})
    return actions


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
    document_actions = _document_actions(documents, entries, seen)
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


# --- Explicit registration scope (Cadastro via API) ------------------------------------------
# Batches created with a scope only touch what the user chose. Batches without one (older batches and
# the Geração em Lote hand-off) keep the plan above, exactly as it was previewed and approved.
SCOPE_KEYS = ("gallery", "documents", "main")
SCOPE_LABELS = {"gallery": "Fotos da galeria", "documents": "Documentos", "main": "Foto principal"}


def normalize_scope(value):
    """{"gallery", "documents", "main"} booleans, at least one true. Also accepts "gallery,documents" or "all"."""
    if isinstance(value, str):
        parts = {p.strip().lower() for p in value.split(",") if p.strip()}
        if parts == {"all"}: parts = set(SCOPE_KEYS)
        if not parts <= set(SCOPE_KEYS):
            raise ValueError("Escopo de cadastro inválido; use Fotos da galeria, Documentos e/ou Foto principal.")
        value = {k: k in parts for k in SCOPE_KEYS}
    if not isinstance(value, dict) or set(value) != set(SCOPE_KEYS) or any(type(v) is not bool for v in value.values()):
        raise ValueError("Escopo de cadastro inválido; use Fotos da galeria, Documentos e/ou Foto principal.")
    if not any(value.values()):
        raise ValueError("Escolha o que deseja cadastrar: Fotos da galeria, Documentos e/ou Foto principal.")
    return {k: value[k] for k in SCOPE_KEYS}


def main_options(candidates, main_from_pattern):
    """Images of the SKU the user may choose as main; the folder pattern only suggests, never chooses."""
    options, seen = [], set()
    for n, c in enumerate(candidates):
        if c["sha256"] in seen: continue
        seen.add(c["sha256"])
        options.append({"sha256": c["sha256"], "name": c["name"], "bytes": c["bytes"], "suggested": main_from_pattern and n == 0})
    return options


def scoped_images(candidates, scope, main_choice, main_from_pattern):
    """Images of the plan for this scope: the explicitly chosen main (if any) + gallery images.

    The image the folder pattern destines to the main never goes to the gallery by itself.
    """
    chosen = None
    if scope["main"] and main_choice:
        chosen = next((c for c in candidates if c["sha256"] == main_choice.get("sha256")), None)
    suggested = candidates[0] if main_from_pattern and candidates else None
    images = [{**chosen, "role": "main_image"}] if chosen else []
    ignored = []
    for c in candidates:
        if c is chosen or not scope["gallery"]: continue
        if c is suggested:
            ignored.append({"name": c["name"], "label": "Principal indicada pela pasta",
                            "reason": "Destinada à principal pelo padrão da pasta; não entra na galeria. "
                                      "Para usá-la, marque Foto principal e escolha este arquivo."})
            continue
        images.append({**c, "role": "gallery"})
    return images, ignored


# Official image naming for raw folders: <SKU>_1.ext = main, <SKU>_2.ext, _3, ... = gallery in numeric order.
IMAGE_RULE = "sku_index"


def image_position(name, sku):
    """Position n of '<SKU>_<n>.<ext>' (SKU compared as an exact string, extension case-insensitive); None otherwise."""
    match = re.fullmatch(re.escape(sku) + r"_(\d+)(\.[A-Za-z0-9]+)", name)
    if not match or match[2].lower() not in IMAGE_EXTENSIONS or int(match[1]) < 1:
        return None
    return int(match[1])


def classify_by_index(candidates, sku):
    """Main = position 1, gallery = positions 2.. sorted numerically (2, 3, 10). Same position twice = ambiguous."""
    positions, outside = {}, []
    for c in candidates:
        n = image_position(c["name"], sku)
        if n is None: outside.append(c)
        else: positions.setdefault(n, []).append(c)
    single = {n: items[0] for n, items in positions.items() if len(items) == 1}
    return {"main": single.get(1), "gallery": [single[n] for n in sorted(single) if n >= 2],
            "duplicates": sorted(n for n, items in positions.items() if len(items) > 1),
            "ambiguous": [c for n, items in sorted(positions.items()) if len(items) > 1 for c in items],
            "outside": outside}


def rule_summary(rule, sku):
    entry = lambda c: {"name": c["name"], "sha256": c["sha256"], "position": image_position(c["name"], sku)}
    return {"rule": IMAGE_RULE, "pattern": f"{sku}_<n>.ext", "main": entry(rule["main"]) if rule["main"] else None,
            "gallery": [entry(c) for c in rule["gallery"]], "duplicates": rule["duplicates"],
            "outside": [c["name"] for c in rule["outside"]]}


def rule_images(rule, scope, main_choice, sku):
    """Plan images by the naming rule. Without <SKU>_1 the main is never guessed: only an explicit manual choice."""
    chosen = rule["main"] if scope["main"] else None
    if scope["main"] and not rule["main"] and main_choice:
        chosen = next((c for c in rule["outside"] + rule["gallery"] if c["sha256"] == main_choice.get("sha256")), None)
    images = [{**chosen, "role": "main_image"}] if chosen else []
    if scope["gallery"]:
        images += [{**c, "role": "gallery"} for c in rule["gallery"] if c is not chosen]
    ignored = [{"name": c["name"], "label": "Fora do padrão",
                "reason": f"Imagem fora do padrão de nomenclatura {sku}_<n>.ext; não classificada como principal ou galeria."}
               for c in rule["outside"] if c is not chosen]
    ignored += [{"name": c["name"], "label": "Posição repetida",
                 "reason": f"Mais de uma imagem encontrada para a posição _{image_position(c['name'], sku)}."} for c in rule["ambiguous"]]
    if rule["main"] and not scope["main"]:
        ignored.append({"name": rule["main"]["name"], "label": "Principal (_1)", "reason": "Foto principal fora do escopo selecionado."})
    return images, ignored


def scoped_file_plan(product, images, documents, scope, main_choice, options, rule=None):
    """Dry Run limited to the chosen scope. Main changes only to <SKU>_1 or to the file explicitly chosen for this SKU."""
    existing = [{"id": i.get("id"), "name": Path(unquote(urlsplit(i.get("src") or "").path)).name}
                for i in product.get("images", [])]
    names = {e["name"].casefold() for e in existing if e["name"]}
    image_actions, seen = [], set()
    for item in images:
        linked = next((e for e in existing if has_identity(e["name"], item["sha256"])), None)
        extra = {}
        if item["sha256"] in seen: action = "duplicate_in_package"
        elif item["role"] == "main_image" and linked:
            action = "already_main" if linked is existing[0] else "promote"
            extra = {"existing_id": linked["id"]}
        elif linked: action = "already_linked"
        elif item["name"].casefold() in names: action = "conflict"
        else: action = "upload"
        seen.add(item["sha256"])
        image_actions.append({"name": item["name"], "role": item["role"], "bytes": item["bytes"], "sha256": item["sha256"],
                              "upload_name": upload_name(item["name"], item["sha256"], item["role"]), "action": action, **extra})
    main_item = next((a for a in image_actions if a["role"] == "main_image"), None)
    gallery_uploads = [a for a in image_actions if a["role"] == "gallery" and a["action"] == "upload"]
    current_main = existing[0] if existing else None
    current = [{"source": "existing", "id": e["id"], "name": e["name"]} for e in existing]
    added = [{"source": "upload", "id": None, "name": a["name"], "status": "pending_upload"} for a in gallery_uploads]
    blockers = []
    choice_required = False
    main = {"in_scope": scope["main"], "current": current_main, "proposed": None, "source": None, "existing_id": None,
            "previous_to_gallery": False, "replacement_available": False, "replacement_order": None}
    if not scope["main"]:
        main["action"] = "preserve" if existing else "none"
        final = current + added
        if not existing and added:
            blockers.append("Produto sem imagem principal: a primeira foto da galeria viraria a principal sem escolha. "
                            "Marque Foto principal e escolha o arquivo.")
    elif main_item is None and not options:
        # Main in scope but the SKU has no image at all: nothing to choose, nothing changes (not an error).
        main["action"] = "unavailable"
        final = current + added
    elif main_item is None:
        main["action"] = "choose"
        choice_required = True
        final = current + added
        blockers.append("A imagem escolhida para principal não está mais no pacote; escolha novamente." if main_choice else
                        f"Foto principal não encontrada no padrão {product.get('sku') or ''}_1.ext." if rule else
                        "Foto principal marcada: escolha a imagem principal deste SKU.")
    elif main_item["action"] == "already_main":
        main.update(action="already_main", proposed={"name": main_item["name"], "id": main_item["existing_id"]})
        final = current + added
    elif main_item["action"] in {"upload", "promote"}:
        source = "upload" if main_item["action"] == "upload" else "existing"
        head = ({"source": "upload", "id": None, "name": main_item["name"], "status": "pending_upload"} if source == "upload"
                else next(c for c in current if c["id"] == main_item["existing_id"]))
        main.update(action="replace" if existing else "set", source=source, existing_id=main_item.get("existing_id"),
                    proposed={"name": main_item["name"], "id": main_item.get("existing_id")},
                    previous_to_gallery=bool(existing))
        final = [head] + [c for c in current if c is not head] + added
    else:
        main["action"] = "blocked"
        final = current + added
    main["final"] = final[0] if final else None
    main["detected"] = bool(rule and rule["main"] and scope["main"])
    main["message"] = {
        "preserve": "Principal atual preservada.", "none": "Produto sem principal; nenhuma será definida.",
        "choose": "Escolha a imagem principal deste SKU.",
        "unavailable": "Nenhuma imagem neste SKU para escolher como principal; principal sem alteração.", "already_main": "A imagem escolhida já é a principal; nada a alterar.",
        "replace": "A imagem principal atual será substituída. A principal atual será preservada na galeria.",
        "set": "Produto sem principal: a imagem escolhida será a principal.", "blocked": "Imagem escolhida em conflito; reconciliar.",
    }[main["action"]]
    if main["detected"]:
        main["message"] = f"Principal detectada automaticamente: {rule['main']['name']}. " + main["message"]
    if rule:
        blockers += [f"Mais de uma imagem encontrada para a posição _{n}." for n in rule["duplicates"]]
    wcda = wcda_state(product)
    entries = wcda["entries"]
    document_actions = _document_actions(documents, entries, seen)
    adding = [d for d in document_actions if d["action"] == "add"]
    if any(i["action"] == "conflict" for i in image_actions):
        blockers.append("Imagem com mesmo nome já vinculada sem identidade PRM; conteúdo não comprovado. Reconciliar para evitar duplicata.")
    if any(d["action"] == "conflict" for d in document_actions):
        blockers.append("Documento com mesmo label/arquivo já no WCDA em outra URL; reconciliar antes de incluir.")
    if adding and wcda["mode"] == "blocked":
        blockers.append("_wcda_arquivos incompatível: " + wcda["reason"])
    uploads = [a for a in image_actions if a["action"] == "upload"]
    changes = bool(uploads or adding or main["action"] in {"replace", "set"})
    empty = [m for k, m in (("gallery", "Galeria: nenhuma imagem nova encontrada."),
                            ("documents", "Nenhum documento novo encontrado para o escopo selecionado."),
                            ("main", "Principal sem alteração.")) if scope[k]]
    nothing = not changes and not blockers
    return {
        "scope": "files_only", "writable_keys": sorted(WRITABLE_KEYS), "protected_fields": PROTECTED_FIELDS,
        "registration_scope": {**scope, "main_choice": main_choice or None},
        "main_options": options, "main_choice_required": choice_required,
        "image_rule": rule_summary(rule, product.get("sku") or "") if rule else None,
        "nothing_to_do": nothing, "nothing_message": " ".join(empty) if nothing else None,
        "images": {"current": existing, "actions": image_actions, "final_order": final, "main_image": main,
                   "gallery_added": len(gallery_uploads)},
        "documents": {"in_scope": scope["documents"], "mode": wcda["mode"], "meta_id": wcda["meta_id"], "reason": wcda.get("reason"),
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


def check_scope(plan):
    """Worker-side guard: the approved files must fit the approved scope. Returns the scope (None for older plans)."""
    dry = plan["dry_run"]
    scope = dry.get("registration_scope")
    if scope is None:
        return None
    inputs = plan.get("input") or {}
    invalid = ValueError("Escopo do cadastro inconsistente com o Dry Run; refaça a prévia. Nada enviado.")
    try:
        normalized = normalize_scope({k: scope.get(k) for k in SCOPE_KEYS})
    except ValueError:
        raise invalid from None
    if (set(scope) != {*SCOPE_KEYS, "main_choice"} or normalized != inputs.get("scope")
            or scope["main_choice"] != (inputs.get("main_choice") or None)):
        raise invalid
    roles = [i["role"] for i in plan["images"]]
    mains = [i for i in plan["images"] if i["role"] == "main_image"]
    if (not scope["gallery"] and "gallery" in roles) or (not scope["documents"] and plan["downloads"]) or len(mains) > 1:
        raise invalid
    rule = dry.get("image_rule")
    if rule is not None:
        check_image_rule(plan, scope, rule)
    elif mains and (not scope["main"] or not scope["main_choice"] or mains[0]["sha256"] != scope["main_choice"]["sha256"]):
        raise invalid
    main = dry["images"]["main_image"]
    if main["action"] in {"replace", "set"} and not (scope["main"] and mains):
        raise invalid
    return scope


def check_image_rule(plan, scope, rule):
    """Worker-side guard for <SKU>_<n>: _1 is the main, _2.. the gallery in numeric order, exactly as approved."""
    sku = plan["dry_run"]["sku"]
    invalid = ValueError(f"Classificação das imagens difere do padrão {sku}_<n>.ext aprovado; refaça a prévia. Nada enviado.")
    if rule.get("rule") != IMAGE_RULE or rule["duplicates"]:
        raise invalid
    if rule["main"] and image_position(rule["main"]["name"], sku) != 1:
        raise invalid
    positions = [image_position(g["name"], sku) for g in rule["gallery"]]
    if any(n is None or n < 2 for n in positions) or positions != sorted(set(positions)):
        raise invalid
    main = None
    if scope["main"] and rule["main"]:
        main = (rule["main"]["name"], rule["main"]["sha256"])
    elif scope["main"] and scope["main_choice"]:
        main = (scope["main_choice"]["name"], scope["main_choice"]["sha256"])
    expected = ([("main_image",) + main] if main else []) + \
               ([("gallery", g["name"], g["sha256"]) for g in rule["gallery"] if (g["name"], g["sha256"]) != main] if scope["gallery"] else [])
    if [(i["role"], i["name"], i["sha256"]) for i in plan["images"]] != expected:
        raise invalid


def folder_inventory(folder):
    """Every file of the SKU folder (relative path + size): renaming, adding or removing one changes it."""
    folder = Path(folder)
    rows = sorted([p.relative_to(folder).as_posix(), p.stat().st_size] for p in folder.rglob("*") if p.is_file())
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode()).hexdigest()


def scoped_order(ids, dry, scope, images, uploaded):
    """Final image IDs for a scoped plan. Main changes only as approved; the previous main stays in the gallery."""
    main = dry["images"]["main_image"]
    gallery = [uploaded[i["sha256"]]["id"] for i in images if i["role"] == "gallery"]
    if main["action"] in {"replace", "set"}:
        if main["source"] == "upload":
            head = next(uploaded[i["sha256"]]["id"] for i in images if i["role"] == "main_image")
        else:
            head = main["existing_id"]
            if head not in ids:
                raise ValueError("Imagem escolhida para principal não está mais vinculada; refaça a prévia. Nada enviado.")
        order = [head] + [i for i in ids if i != head] + gallery
    else:
        if any(i["role"] == "main_image" for i in images):
            raise ValueError("Principal fora do Dry Run aprovado; nada enviado.")
        order = ids + gallery
    order = list(dict.fromkeys(order))
    if not scope["main"] and (order[:1] != ids[:1]):
        raise ValueError("A principal só muda com Foto principal no escopo aprovado; nada enviado.")
    if not scope["gallery"] and set(order) - set(ids) - set(order[:1]):
        raise ValueError("Galeria fora do escopo aprovado; nada enviado.")
    return order
