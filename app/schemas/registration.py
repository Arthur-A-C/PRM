"""One reviewed product representation for exports and future integrations."""

from __future__ import annotations

from typing import Literal
from html.parser import HTMLParser

from pydantic import BaseModel, Field, field_validator, model_validator


CompanyCode = Literal["choice", "sag", "portwell"]


class _SafeHtml(HTMLParser):
    allowed = {"h1", "h2", "h3", "p", "ul", "ol", "li", "strong", "em", "br", "table", "thead", "tbody", "tr", "th", "td"}
    void = {"br"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag not in self.allowed or attrs:
            raise ValueError("HTML contém elemento ou atributo não permitido.")
        if tag not in self.void:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack.pop() != tag:
            raise ValueError("HTML com tags fora de ordem.")

    def handle_startendtag(self, tag, attrs):
        if tag not in self.void or attrs:
            raise ValueError("HTML autocontido não permitido.")

    def handle_comment(self, data):
        raise ValueError("Comentários HTML não são permitidos.")


def validate_html_fragment(value: str) -> str:
    parser = _SafeHtml()
    parser.feed(value)
    parser.close()
    if parser.stack:
        raise ValueError("HTML com tags não fechadas.")
    return value


class ProductAttribute(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    values: list[str] = Field(min_length=1)
    visible: bool = True
    global_attribute: bool = False

    @field_validator("values")
    @classmethod
    def nonempty_values(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values if value.strip() and value.strip() != "-"]
        if not cleaned:
            raise ValueError("Attribute requires at least one nonempty value.")
        return cleaned


class ProductFile(BaseModel):
    role: Literal[
        "main_image", "gallery", "source_datasheet", "generated_datasheet",
        "drawing_3d", "manual", "certificate", "other",
    ]
    filename: str
    sha256: str | None = None


class RegistrationProduct(BaseModel):
    company: CompanyCode
    cigam_code: str = Field(min_length=1, max_length=255)
    sku: str = Field(min_length=1, max_length=255)
    technical_name: str = Field(min_length=1)
    commercial_title: str = Field(min_length=1)
    supplier: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    category_paths: list[str] = Field(default_factory=list)
    short_description: str | None = None
    full_description: str | None = None
    features: list[str] = Field(default_factory=list)
    specifications: dict[str, str] = Field(default_factory=dict)
    benefits: list[str] = Field(default_factory=list)
    applications: list[str] = Field(default_factory=list)
    attributes: list[ProductAttribute] = Field(default_factory=list)
    compatible_models: list[str] = Field(default_factory=list)
    component_codes: list[str] = Field(default_factory=list)
    files: list[ProductFile] = Field(default_factory=list)
    cigam_fields: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, str] = Field(default_factory=dict)
    validation_status: Literal["draft", "needs_review", "approved"] = "draft"
    warnings: list[str] = Field(default_factory=list)

    @field_validator("sku", "cigam_code", mode="before")
    @classmethod
    def keep_code_as_text(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("SKU/CIGAM code must be supplied as text to preserve leading zeros.")
        if not value or value != value.strip() or value.startswith(("=", "+", "-", "@")):
            raise ValueError("Invalid or unsafe SKU/CIGAM code.")
        return value

    @field_validator("short_description", "full_description")
    @classmethod
    def safe_html(cls, value: str | None) -> str | None:
        return validate_html_fragment(value) if value else value

    @model_validator(mode="after")
    def codes_agree(self):
        if self.sku != self.cigam_code:
            raise ValueError("SKU must match CIGAM code.")
        if len(self.attributes) > 15:
            raise ValueError("At most 15 WooCommerce attributes are allowed.")
        return self
