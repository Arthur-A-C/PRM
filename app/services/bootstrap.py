from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Company, Organization


INITIAL_COMPANIES = (
    {"code": "portwell", "name": "Portwell", "domain": None, "company_type": "nossa"},
    {"code": "choice-tech", "name": "Choice Tech", "domain": None, "company_type": "nossa"},
    {"code": "eco-automacao", "name": "Eco Automação", "domain": "ecoautomacao.com.br", "company_type": "concorrente"},
)


def ensure_reference_data(db: Session, settings: Settings) -> tuple[Organization, dict[str, Company]]:
    organization = db.scalar(
        select(Organization).where(Organization.name == settings.organization_name)
    )
    if organization is None:
        organization = Organization(
            name=settings.organization_name,
            timezone=settings.organization_timezone,
        )
        db.add(organization)
        db.flush()

    companies = {
        company.code: company
        for company in db.scalars(
            select(Company).where(Company.organization_id == organization.id)
        )
    }
    for company_data in INITIAL_COMPANIES:
        company = companies.get(company_data["code"])
        if company is None:
            company = Company(organization_id=organization.id, active=True, **company_data)
            db.add(company)
            companies[company.code] = company
        else:
            company.name = company_data["name"]
            company.domain = company_data["domain"]
            company.company_type = company_data["company_type"]
            company.active = True
    db.flush()
    return organization, companies
