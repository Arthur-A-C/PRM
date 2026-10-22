"""Read-only authentication/model check. Never prints credentials or provider bodies."""
import json
from pathlib import Path

import anthropic
from dotenv import dotenv_values


def main():
    values = dotenv_values(Path(__file__).resolve().parents[1] / '.env')
    key = values.get('ANTHROPIC_API_KEY') or ''
    model = values.get('DATASHEET_MODEL')
    if not key.startswith('sk-ant-') or key != key.strip():
        print(json.dumps({'authenticated': False, 'reason': 'unexpected_key_format'}))
        return
    try:
        with anthropic.Anthropic(api_key=key, base_url='https://api.anthropic.com',
                                 timeout=20, max_retries=0) as client:
            models = list(client.models.list(limit=100))
            print(json.dumps({'authenticated': True, 'configured_model': model,
                              'exact_model_listed': any(item.id == model for item in models),
                              'available_opus_models': [item.id for item in models if 'opus' in item.id]}))
    except anthropic.APIStatusError as error:
        print(json.dumps({'authenticated': False, 'status': error.status_code,
                          'error_type': type(error).__name__}))
    except Exception as error:
        print(json.dumps({'check_failed': True, 'error_type': type(error).__name__}))


if __name__ == '__main__':
    main()
