"""One origin vocabulary over the existing Company ownership model."""
from sqlalchemy import select
from app.models import Company

GROUP_TYPES = {"internal": "nossa", "competitor": "concorrente"}
GROUP_LABELS = {"internal": "Nossa base", "competitor": "Concorrência"}


def source_group(company_type):
    for group, value in GROUP_TYPES.items():
        if value == company_type:
            return group
    raise ValueError("Tipo de empresa desconhecido")


def resolve_origin(db, organization_id, company_id, group, *, lock=False):
    if group not in GROUP_TYPES:
        raise ValueError("Selecione Nossa base ou Concorrência.")
    statement = select(Company).where(
        Company.id == company_id, Company.organization_id == organization_id,
        Company.active.is_(True), Company.company_type == GROUP_TYPES[group],
    )
    if lock:
        statement = statement.with_for_update()
    company = db.scalar(statement)
    if company is None:
        raise LookupError("Origem indisponível nesta organização ou incompatível com o grupo.")
    return company
