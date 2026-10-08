"""Extra HTTP Basic gate for short-lived public previews only.

Run this ASGI app with PRM_PREVIEW_BASIC_PASSWORD and secure cookies enabled.
The ordinary local app remains unchanged.
"""

import os

from app.main import app as prm_app
from app.services.preview_auth import PreviewBasicAuth


preview_password = os.environ.get("PRM_PREVIEW_BASIC_PASSWORD", "")
if not preview_password:
    raise RuntimeError("PRM_PREVIEW_BASIC_PASSWORD deve ser configurada apenas no processo remoto.")
app = PreviewBasicAuth(prm_app, preview_password)
