"""Read-only audit of memory, storage and OS in the published database."""
import json
from collections import Counter
from sqlalchemy import create_engine, select, text
from app.config import get_settings
from app.models import Organization, RefinedCatalogRun, RefinedCatalogItem
from app.services.attribute_dictionary import attribute_name


def main():
    settings = get_settings()
    engine = create_engine(settings.database_url)
    counts, samples, pairs, os_scopes = Counter(), {}, Counter(), Counter()
    with engine.connect() as conn:
        conn.execute(text('SET TRANSACTION READ ONLY'))
        org = conn.scalar(select(Organization.id).where(Organization.name == settings.organization_name))
        run = conn.scalar(select(RefinedCatalogRun.id).where(RefinedCatalogRun.organization_id == org, RefinedCatalogRun.status == 'published'))
        total = 0
        for item in conn.execution_options(stream_results=True).scalars(select(RefinedCatalogItem.payload).where(RefinedCatalogItem.run_id == run)):
            total += 1
            names = set()
            for a in item['attribute_observations']:
                name = attribute_name(a['raw_name'])
                if a['attribute_code'] == 'compute.os':
                    os_scopes[(item['source_id'], a['configuration_scope'])] += 1
                if len(name) < 80 and (any(t in name for t in ['memoria', 'armazenamento']) or name in {'os', 'sistema operativo', 'sistema operacional'}):
                    key = (item['source_id'], a['raw_name'], a['attribute_code'])
                    counts[key] += 1
                    samples.setdefault(key, [])
                    if len(samples[key]) < 4 and a['raw_value'] not in samples[key]:
                        samples[key].append(a['raw_value'])
                    names.add(name)
            for base in ['memoria', 'armazenamento']:
                if base in names and 'tipo de ' + base in names:
                    pairs[(item['source_id'], base)] += 1
    print(json.dumps({'run_id': run, 'items': total, 'os_scopes': {str(k): v for k,v in os_scopes.items()}, 'cooccurrence': {str(k): v for k,v in pairs.items()},
                      'fields': [{'source': k[0], 'name': k[1], 'code': k[2], 'count': v, 'examples': samples[k]} for k,v in counts.most_common()]}, ensure_ascii=True))


if __name__ == '__main__':
    main()
