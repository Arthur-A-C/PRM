"""Explicit publication of registered offers into the existing refined snapshot tables."""
import hashlib
import json
import re
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import func, select, text
from app.models import Company, Offer, CatalogImport, ImportRow, OfferObservation, OfferPrice, Brand, OfferEnrichment, OfferAttribute, AttributeDefinition
from app.models.refined_catalog import RefinedCatalogRun, RefinedCatalogItem, RefinedCatalogRaw
from app.services.refined_catalog import load_policy, normalize_record, normalize_attribute, plain, fingerprint
from app.services.refined_catalog_database import database_manifest, activate_run


# Known companies keep the source codes used by the dashboard, CSS and filters; others get a short stable id.
SOURCE_ALIASES = {'portwell': 'portwell', 'choice': 'choice', 'choice-tech': 'choice', 'sag': 'sag',
                  'eco': 'eco', 'eco-automacao': 'eco', 'dimensional': 'dimensional'}


def source_code(company):
    return SOURCE_ALIASES.get(company['code']) or 'c' + company['id'].replace('-', '')[:19]


def lock_catalog(db, organization_id):
    if db.get_bind().dialect.name == 'postgresql':
        db.execute(text('SELECT pg_advisory_xact_lock(hashtext(:key))'), {'key': 'refined:' + str(organization_id)})


def capture(db, organization_id):
    """Capture all input values, not only counts; no files, network, or AI."""
    companies = list(db.scalars(select(Company).where(Company.organization_id == organization_id, Company.active.is_(True)).order_by(Company.id)))
    offers = list(db.scalars(select(Offer).where(Offer.organization_id == organization_id,
        Offer.company_id.in_([c.id for c in companies]), Offer.active.is_(True), Offer.excluded_from_analytics.is_(False)).order_by(Offer.id)))
    ids = [o.id for o in offers]
    batches = list(db.scalars(select(CatalogImport).where(CatalogImport.organization_id == organization_id, CatalogImport.status == 'published').order_by(CatalogImport.created_at, CatalogImport.id)))
    raw, origin_batches = {}, {}
    for row in db.scalars(select(ImportRow).join(CatalogImport, CatalogImport.id == ImportRow.catalog_import_id).where(
            CatalogImport.organization_id == organization_id, ImportRow.offer_id.in_(ids), ImportRow.published.is_(True))
            .order_by(CatalogImport.created_at, CatalogImport.id)):
        raw[str(row.offer_id)] = row.raw_row
        origin_batches[str(row.offer_id)] = str(row.catalog_import_id)
    prices = defaultdict(dict)
    for price, observation in db.execute(select(OfferPrice, OfferObservation).join(OfferObservation, OfferObservation.id == OfferPrice.observation_id)
            .where(OfferObservation.offer_id.in_(ids)).order_by(OfferObservation.imported_at, OfferObservation.id)):
        prices[str(observation.offer_id)][price.modality] = {'kind': price.modality, 'amount': str(price.amount) if price.amount is not None else None,
            'raw_value': price.raw_value, 'state': price.state, 'visibility': 'public'}
    attrs = defaultdict(list)
    for a, definition in db.execute(select(OfferAttribute, AttributeDefinition).join(AttributeDefinition, AttributeDefinition.id == OfferAttribute.definition_id)
            .where(OfferAttribute.offer_id.in_(ids), OfferAttribute.review_status != 'rejeitado').order_by(OfferAttribute.id)):
        value = a.value_text if a.value_text is not None else a.value_numeric if a.value_numeric is not None else a.value_boolean
        if value is not None:
            attrs[str(a.offer_id)].append((definition.name, str(value)))
    # Rule-based enrichment (already reviewed import pipeline) is the main attribute source of ERP/scraped catalogs.
    for enrichment in db.scalars(select(OfferEnrichment).where(OfferEnrichment.offer_id.in_(ids)).order_by(OfferEnrichment.offer_id)):
        for key, value in sorted((enrichment.attributes or {}).items()):
            if value not in (None, '', [], {}):
                attrs[str(enrichment.offer_id)].append((key.replace('_', ' '), value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)))
    brands = {str(b.id): b.canonical_name for b in db.scalars(select(Brand).where(Brand.organization_id == organization_id))}
    records = [{**{col.name: str(getattr(o, col.name)) if getattr(o, col.name) is not None else None for col in Offer.__table__.columns},
                'raw': raw.get(str(o.id), {}), 'import_id': origin_batches.get(str(o.id)),
                'prices': list(prices[str(o.id)].values()), 'attributes': attrs[str(o.id)],
                'canonical_brand': brands.get(str(o.brand_id), o.brand_raw)} for o in offers]
    sources = [{'id': str(c.id), 'name': c.name, 'code': c.code, 'kind': 'own' if c.company_type == 'nossa' else 'competitor'} for c in companies]
    imports = [{'id': str(b.id), 'company_id': str(b.company_id), 'file': b.original_filename, 'sha256': b.file_sha256,
                'created_at': b.created_at.isoformat()} for b in batches]
    data = {'companies': sources, 'records': records, 'imports': imports}
    return data, fingerprint(data)


def catalog_stamp(db, organization_id):
    """Cheap change detector for page renders (counts + latest timestamps). The full capture hash still gates publishing."""
    org = organization_id
    parts = [db.execute(select(Company.id, Company.company_type, Company.active, Company.updated_at)
                        .where(Company.organization_id == org).order_by(Company.id)).all(),
             db.execute(select(func.count(Offer.id), func.max(Offer.updated_at)).where(Offer.organization_id == org)).one(),
             db.execute(select(func.count(OfferPrice.id), func.max(OfferPrice.updated_at)).join(OfferObservation, OfferObservation.id == OfferPrice.observation_id)
                        .join(Offer, Offer.id == OfferObservation.offer_id).where(Offer.organization_id == org)).one(),
             db.execute(select(func.count(OfferAttribute.id), func.max(OfferAttribute.updated_at)).join(Offer, Offer.id == OfferAttribute.offer_id)
                        .where(Offer.organization_id == org)).one(),
             db.execute(select(func.count(ImportRow.id), func.max(ImportRow.updated_at)).join(CatalogImport, CatalogImport.id == ImportRow.catalog_import_id)
                        .where(CatalogImport.organization_id == org)).one(),
             db.execute(select(func.count(OfferEnrichment.id), func.max(OfferEnrichment.updated_at)).join(Offer, Offer.id == OfferEnrichment.offer_id)
                        .where(Offer.organization_id == org)).one(),
             db.execute(select(func.count(Brand.id), func.max(Brand.updated_at)).where(Brand.organization_id == org)).one()]
    return fingerprint([[str(v) for v in row] for part in parts for row in (part if isinstance(part, list) else [part])])


def publication_status(db, organization_id):
    """Page-render status: aggregate queries only (no full capture of every offer)."""
    counts = dict(db.execute(select(Company.company_type, func.count(Offer.id)).join(Offer, Offer.company_id == Company.id).where(
        Company.organization_id == organization_id, Company.active.is_(True), Offer.organization_id == organization_id,
        Offer.active.is_(True), Offer.excluded_from_analytics.is_(False)).group_by(Company.company_type)).all())
    internal, competitor = counts.get('nossa', 0), sum(v for k, v in counts.items() if k != 'nossa')
    last_import = db.scalar(select(func.max(CatalogImport.created_at)).where(CatalogImport.organization_id == organization_id,
                                                                            CatalogImport.status == 'published'))
    manifest = database_manifest(db, organization_id)
    stamp = catalog_stamp(db, organization_id)
    return {'internal': internal, 'competitor': competitor, 'can_publish': bool(internal and competitor),
            'last_import': last_import.isoformat() if last_import else None,
            'last_published': manifest.get('created_at') if manifest else None,
            'run_id': manifest.get('run_id') if manifest else None,
            'registered': bool(manifest and manifest.get('origin') == 'registered_catalog'),
            'pending': bool(internal or competitor) and (not manifest or manifest.get('catalog_stamp') != stamp)}


def build_snapshot(data, organization_id, actor_id, version, actor_name=None, stamp=None):
    policy = load_policy()
    now = datetime.now(timezone.utc).isoformat()
    run_id = uuid.uuid4().hex[:24]
    # Short stable source IDs fit the existing VARCHAR(20), including new competitors.
    used = {r['company_id'] for r in data['records']}
    sources = {source_code(c): c for c in data['companies'] if c['id'] in used}
    if len(sources) != len(used):
        raise ValueError('Duas empresas usam o mesmo código de origem. Ajuste os códigos antes de publicar.')
    company_source = {c['id']: code for code, c in sources.items()}
    counts, families, items, raw_records = {}, {}, [], []
    for source in sources:
        counts[source] = dict.fromkeys(['received','accepted','public_catalog','with_attributes','unknown_family','conflicting_attributes','attributes','unmapped_attributes','quarantine'], 0)
    for row in data['records']:
        source = company_source[row['company_id']]
        raw = row['raw']
        pairs = list(row['attributes'])
        for key, value in raw.items():
            match = re.fullmatch(r'Nome do atributo (\d+)', key)
            if match and value and raw.get('Valores do atributo ' + match[1]):
                pairs.append((str(value), str(raw['Valores do atributo ' + match[1]])))
            elif key.startswith('ATR_') and value not in (None, ''):
                pairs.append((key, str(value)))
        # Adapter reuses the established normalization, including USB, RAM and OS.
        normalized_input = {'ID': row['id'], 'SKU': row['external_code'], 'Nome': row['name_raw'],
            'Marcas': row['canonical_brand'], 'Categorias': row['category_raw'] or '',
            'Descrição': row['description_raw'] or row['application_raw'] or '',
            'Publicado': '1', 'Visibilidade no catálogo': 'visible'}
        for index, (name, value) in enumerate(dict.fromkeys(pairs), 1):
            normalized_input['Nome do atributo ' + str(index)] = name
            normalized_input['Valores do atributo ' + str(index)] = value
        item, attributes = normalize_record({'raw': normalized_input, 'issues': []}, 'portwell', policy, row['import_id'] or version[:24])
        item.update(item_id=row['id'], source_id=source, source_group='internal' if sources[source]['kind'] == 'own' else 'competitor',
            source_name=sources[source]['name'], record_key=row['external_code'], url=row['source_url'],
            segment=row['subcategory_raw'], offer_id=row['id'], attribute_observations=attributes)
        item['title_search'] = plain(' '.join(str(v or '') for v in [row['name_raw'], row['external_code'], row['canonical_brand'], row['category_raw'], row['subcategory_raw']]))
        item['commercial'].update(prices=row['prices'], availability_raw=row['availability_raw'], availability_state=row['availability_state'], stock_raw=row['stock_quantity'])
        for attr in attributes:
            attr['item_id'] = row['id']
            for evidence in attr['evidence']:
                evidence.update(source_id=source, record_key=row['external_code'], source_layer='registered_catalog')
        item['normalized_hash'] = fingerprint(item)
        c = counts[source]
        for key in ('received','accepted','public_catalog'):
            c[key] += 1
        c['with_attributes'] += bool(attributes)
        c['attributes'] += len(attributes)
        c['unmapped_attributes'] += sum(not a['mapped'] for a in attributes)
        c['conflicting_attributes'] += sum(a['knowledge_state'] == 'conflicting' for a in attributes)
        classification = item['classification']
        c['unknown_family'] += classification['family_id'] == 'unknown'
        family = families.setdefault(classification['family_id'], {'label': classification['family_label'], 'proximity': classification['proximity'], 'counts': {}, 'public_counts': {}})
        for key in ('counts','public_counts'):
            family[key][source] = family[key].get(source, 0) + 1
        items.append(item)
        raw_records.append({'source_id': source, 'position': len(raw_records)+1, 'payload': row})
    manifest = {'run_id': run_id, 'created_at': now, 'schema_version': 1, 'rule_version': policy['rule_version'],
        'origin': 'registered_catalog', 'catalog_version': version, 'catalog_stamp': stamp, 'source_registry': sources,
        'counts': counts, 'families': families, 'inputs': data['imports'], 'matching_status': 'not_assessed',
        'ai_calls': 0, 'elapsed_seconds': 0, 'attribute_analysis': None,
        'audit': {'organization_id': str(organization_id), 'user_id': str(actor_id), 'user_name': actor_name, 'published_at': now,
                  'internal_count': sum(counts[s]['accepted'] for s,c in sources.items() if c['kind']=='own'),
                  'competitor_count': sum(counts[s]['accepted'] for s,c in sources.items() if c['kind']=='competitor'),
                  'companies': list(sources.values()), 'import_ids': sorted({r['import_id'] for r in data['records'] if r['import_id']})}}
    return manifest, items, raw_records


def publish_registered(db, organization_id, actor_id, expected_version, actor_name=None):
    """New run is validated and activated in the caller's transaction: any failure rolls back and the previous
    published snapshot stays active (activation archives it only after the new run reconciles)."""
    lock_catalog(db, organization_id)
    data, version = capture(db, organization_id)
    if version != expected_version:
        raise ValueError('O catálogo mudou. Revise a base novamente antes de publicar.')
    kinds = {c['id']: c['kind'] for c in data['companies']}
    if {kinds[r['company_id']] for r in data['records']} != {'own', 'competitor'}:
        raise ValueError('Importe ao menos um produto interno e um concorrente antes de publicar.')
    old = database_manifest(db, organization_id)
    if old and old.get('catalog_version') == version:
        return old
    manifest, items, raws = build_snapshot(data, organization_id, actor_id, version, actor_name, catalog_stamp(db, organization_id))
    db.add(RefinedCatalogRun(id=manifest['run_id'], organization_id=organization_id, status='validated', manifest=manifest))
    db.flush()
    for item in items:
        db.add(RefinedCatalogItem(run_id=manifest['run_id'], item_id=uuid.UUID(item['item_id']), source_id=item['source_id'],
               record_key=item['record_key'], title_search=item['title_search'], family_id=item['classification']['family_id'], public_catalog=True, payload=item))
    for raw in raws:
        db.add(RefinedCatalogRaw(run_id=manifest['run_id'], **raw))
    db.flush()
    db.expire_all()
    if capture(db, organization_id)[1] != version:
        raise ValueError('Dados alterados durante a geração. Nenhuma análise foi substituída.')
    activate_run(db, organization_id, manifest['run_id'])
    return manifest
