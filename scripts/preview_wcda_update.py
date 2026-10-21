"""GET-only inspection and dry run. This CLI has no execution/upload flag."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.store_config import StoreSettings, COMPANIES
from app.services.registration_woo_api import WooClient, credentials_for
from app.services.store_document_update import prepare_document_update, preview


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--company', required=True, choices=COMPANIES)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--sku')
    target.add_argument('--product-id', type=int, help='Somente inspeção; não autoriza esse produto')
    parser.add_argument('--documents', type=Path, help='Lista JSON de documentos REAIS com URL pública já existente')
    args = parser.parse_args()
    additions = []
    if args.documents:
        if args.documents.stat().st_size > 1024 * 1024:
            raise ValueError('Lista de documentos acima do limite.')
        additions = json.loads(args.documents.read_text(encoding='utf-8-sig'))
    settings = StoreSettings()
    credentials = credentials_for(args.company, settings)
    client = WooClient(credentials, timeout=settings.timeout)
    try:
        product = client.product(args.product_id) if args.product_id else client.find_by_sku(args.sku)
        if not product:
            raise ValueError('SKU não encontrado.')
        plan = prepare_document_update(args.company, credentials.base_url, product, args.sku or product.get('sku'), additions)
        print(json.dumps(preview(plan), ensure_ascii=True, indent=2))
    finally:
        client.close()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('Prévia não gerada. Confira empresa, SKU, credenciais e os quatro campos reais dos documentos. Nenhuma escrita executada.')
        raise SystemExit(1)
