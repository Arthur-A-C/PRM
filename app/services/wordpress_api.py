"""WordPress application-password client. Uploads intentionally not implemented."""
from app.services.store_http import http_client, read_json


class WordPressClient:
    def __init__(self, credentials, *, timeout=20, transport=None):
        self.client = http_client(credentials.base_url, "wp/v2",
            auth=(credentials.username, credentials.password), timeout=timeout, transport=transport)

    def close(self):
        self.client.close()

    def identity(self):
        result = read_json(self.client, "users/me", {"context": "edit", "_fields": "id,capabilities"})
        if not isinstance(result, dict) or type(result.get("id")) is not int or result["id"] <= 0:
            raise ValueError("Identidade autenticada não confirmada.")
        return result

    def media(self):
        result = read_json(self.client, "media", {"context": "edit", "per_page": 1, "_fields": "id"})
        if not isinstance(result, list):
            raise ValueError("Resposta de mídia inválida.")
        return result
