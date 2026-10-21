"""Lossless reading of _wcda_arquivos; no write payload or serialization guesses."""
from copy import deepcopy
from urllib.parse import urlsplit


def interpret_documents(product):
    metadata=product.get("meta_data",[])
    warnings=[]
    if not isinstance(metadata,list):
        return {"present":False,"documents":[],"warnings":["meta_data não é lista."],"raw_metadata":[],"write_verified":False}
    fields=[deepcopy(m) for m in metadata if isinstance(m,dict) and m.get("key")=="_wcda_arquivos"]
    if len(fields)>1: warnings.append("Mais de uma metadata com a mesma chave; não mesclar automaticamente.")
    documents=[]
    for field in fields:
        value=field.get("value")
        if not isinstance(value,list):
            warnings.append("Valor não é lista; não desserializar nem converter automaticamente.")
            continue
        for position,entry in enumerate(value):
            if not isinstance(entry,dict):
                warnings.append("Entrada de documento não é objeto.")
                continue
            url=entry.get("url")
            safe=False
            if isinstance(url,str):
                try:
                    parsed=urlsplit(url)
                    safe=parsed.scheme in {"http","https"} and bool(parsed.hostname) and not parsed.username and not parsed.password
                except ValueError: pass
            if not safe: warnings.append(f"Documento na posição {position}: URL ausente ou inválida.")
            identifiers={k:deepcopy(entry[k]) for k in ("id","attachment_id","media_id","file_id") if k in entry}
            documents.append({"position":position,"metadata_id":field.get("id"),
                "label":entry.get("label"),"url":url,"url_valid":safe,"filename":entry.get("filename"),
                "filesize":entry.get("filesize"),"identifier_candidates":identifiers,
                "explicit_order_candidates":{k:deepcopy(entry[k]) for k in ("order","position","sort_order") if k in entry},
                "raw":deepcopy(entry)})
    return {"present":bool(fields),"documents":documents,"warnings":warnings,
            "raw_metadata":fields,"write_verified":False,
            "order_semantics":"posição na lista REST; ordem visual do plugin não confirmada"}


def document_dry_run(product, proposed):
    """Report, not a write payload. Same filename/label is not proof of equality."""
    current=interpret_documents(product)
    actions=[]
    for item in proposed:
        label=item.get("label")
        filename=item.get("name") or item.get("filename")
        candidates=[d for d in current["documents"] if
                    (label and d["label"]==label) or (filename and d["filename"]==filename)]
        actions.append({"label":label,"filename":filename,
                        "action":"reconcile_existing" if candidates else "pending_contract",
                        "candidate_positions":[d["position"] for d in candidates],
                        "content_equality_verified":False})
    return {"dry_run":True,"writes_allowed":False,"existing_count":len(current["documents"]),
            "preserve_existing":True,"actions":actions,"warnings":current["warnings"],
            "blocker":"Contrato de gravação de _wcda_arquivos não homologado."}
