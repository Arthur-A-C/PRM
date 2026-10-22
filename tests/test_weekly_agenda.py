"""Pauta Semanal: GitHub (simulado), Planner, regras de situação, IA (simulada), edições, ciclo de vida, agenda e API."""
import io
import json
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.models.identity import Organization, User
from app.models.meetings import Activity, ActivityAudit, Meeting, MeetingRun, TranscriptRevision
from app.models.weekly_agenda import WeeklyAgenda, WeeklyAgendaRevision, WeeklyAgendaSettings
from app.services import github_activity as gh
from app.services import weekly_agenda as agendas

SP = ZoneInfo("America/Sao_Paulo")
MONDAY = date(2026, 10, 19)
NOW = datetime(2026, 10, 23, 10, 0, tzinfo=SP).astimezone(timezone.utc)  # Friday morning
TOKEN = "ghp_" + "S3cr3tT0k3n" * 4
DEPLOYED = "d" * 40
REPO = "/repos/Arthur-A-C/PRM"


def sha(char):
    return char * 40


def at(day, hour=12):
    return datetime(2026, 10, day, hour, tzinfo=SP).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def pr(number, title, *, state="open", merged=None, closed=None, created=at(20), updated=None, draft=False, labels=(), reviewers=(), head=None,
       author="Kaue-Borges"):
    return {"number": number, "title": title, "state": state, "draft": draft, "user": {"login": author}, "assignees": [],
            "requested_reviewers": [{"login": r} for r in reviewers], "labels": [{"name": l} for l in labels], "created_at": created,
            "updated_at": updated or merged or closed or created, "closed_at": closed or merged, "merged_at": merged,
            "html_url": f"https://github.com/Arthur-A-C/PRM/pull/{number}", "head": {"ref": f"feature/{number}", "sha": head or sha(str(number % 10))},
            "base": {"ref": "main"}, "merge_commit_sha": sha("abcdef"[number % 6]) if merged else None}


class FakeGitHub:
    """Metadata endpoints of the GitHub REST API for one week of activity. Any other path fails the test."""

    def __init__(self):
        self.pulls = [
            pr(1, "Infraestrutura Docker isolada", state="closed", merged=at(20), created=at(16)),
            pr(2, "fix: corrige caminho da imagem principal", state="closed", merged=at(21), labels=["bug"]),
            pr(3, "Seleção de pastas do computador", created=at(22), reviewers=["Arthur-A-C"]),
            pr(4, "Remoção de arquivos em produção", created=at(22), author="arthur-dev"),
            pr(5, "Experimento descartado", state="closed", closed=at(21), created=at(20)),
            pr(6, "Refatoração antiga ainda aberta", created="2026-09-01T12:00:00Z", updated="2026-09-02T12:00:00Z"),
            pr(7, "Entrega de outubro", state="closed", merged="2026-10-01T12:00:00Z", created="2026-09-30T12:00:00Z"),
        ]
        self.commits = {
            "main": [{"sha": sha("1"), "commit": {"message": "Merge PR #1", "author": {"name": "Kaue", "date": at(20)}}, "author": {"login": "Kaue-Borges"}},
                     {"sha": sha("e"), "commit": {"message": "fix: ajusta texto do rodapé token=" + TOKEN, "author": {"name": "Kaue", "date": at(21)}},
                      "author": {"login": "Kaue-Borges"}}],
            "feature/3": [{"sha": sha("3"), "commit": {"message": "feat(envios): pastas", "author": {"name": "Kaue", "date": at(22)}}, "author": {"login": "Kaue-Borges"}}],
            "feature/rascunho": [{"sha": sha("f"), "commit": {"message": "wip: pauta semanal\n\ncorpo longo", "author": {"name": "Daniel", "date": at(22)}},
                                  "author": {"login": "daniel-dev"}}],
        }
        self.pr_commits = {1: [sha("1")], 2: [sha("2")], 3: [sha("3")], 4: [sha("4")], 5: [sha("5")], 6: [sha("6")]}
        self.issues = [
            {"number": 10, "title": "Erro ao exportar CSV", "state": "open", "labels": [{"name": "bug"}], "user": {"login": "daniel-dev"},
             "assignees": [{"login": "daniel-dev"}], "created_at": at(19), "updated_at": at(21), "html_url": "https://github.com/Arthur-A-C/PRM/issues/10"},
            {"number": 11, "title": "Foto principal duplicada", "state": "closed", "state_reason": "completed", "labels": [{"name": "bug"}],
             "user": {"login": "arthur-dev"}, "assignees": [], "created_at": at(19), "closed_at": at(22), "updated_at": at(22),
             "html_url": "https://github.com/Arthur-A-C/PRM/issues/11"},
            {"number": 12, "title": "Usar TLS no gateway?", "state": "open", "labels": [{"name": "decisão"}], "user": {"login": "Kaue-Borges"},
             "assignees": [], "created_at": at(20), "updated_at": at(20), "html_url": "https://github.com/Arthur-A-C/PRM/issues/12",
             "milestone": {"due_on": "2026-10-28T12:00:00Z"}},
            {"number": 13, "title": "Ideia descartada", "state": "closed", "state_reason": "not_planned", "labels": [], "user": {"login": "arthur-dev"},
             "assignees": [], "created_at": at(19), "closed_at": at(20), "updated_at": at(20), "html_url": "https://github.com/Arthur-A-C/PRM/issues/13"},
            {"number": 3, "title": "PR as issue", "state": "open", "labels": [], "pull_request": {}, "user": {"login": "x"}, "assignees": []},
        ]
        self.checks = {sha("3"): [{"name": "Python tests", "status": "completed", "conclusion": "success"}],
                       sha("4"): [{"name": "Python tests", "status": "completed", "conclusion": "failure"}],
                       sha("1"): [{"name": "Python tests", "status": "completed", "conclusion": "success"}]}
        self.deployed_contains = {sha("b")}  # merge commit of PR #1 (1 % 6 -> "b")
        self.paths, self.headers = [], []
        self.fail = None

    def handle(self, request):
        path, params = request.url.path, request.url.params
        self.paths.append(path); self.headers.append(dict(request.headers))
        assert request.method == "GET", "the agenda never writes to GitHub"
        assert "/contents" not in path and "/git/" not in path, "file contents are never read"
        if self.fail:
            return self.fail(request)
        if path == REPO:
            return httpx.Response(200, json={"full_name": "Arthur-A-C/PRM", "private": True, "default_branch": "main"},
                                  headers={"x-oauth-scopes": "repo, workflow"})
        if path == REPO + "/pulls":
            rows = [p for p in self.pulls if params["state"] == "all" or p["state"] == "open"]
            return httpx.Response(200, json=sorted(rows, key=lambda p: p["updated_at"], reverse=True))
        if m := re.fullmatch(REPO + r"/pulls/(\d+)/commits", path):
            return httpx.Response(200, json=[{"sha": s} for s in self.pr_commits.get(int(m.group(1)), [])])
        if path == REPO + "/branches":
            return httpx.Response(200, json=[{"name": n} for n in self.commits])
        if path == REPO + "/commits":
            return httpx.Response(200, json=[{**c, "html_url": f"https://github.com/Arthur-A-C/PRM/commit/{c['sha']}"} for c in self.commits[params["sha"]]])
        if path == REPO + "/issues":
            rows = [i for i in self.issues if params["state"] == "all" or i["state"] == "open"]
            return httpx.Response(200, json=rows)
        if m := re.fullmatch(REPO + r"/commits/([0-9a-f]+)/check-runs", path):
            return httpx.Response(200, json={"check_runs": self.checks.get(m.group(1), [])})
        if m := re.fullmatch(REPO + r"/compare/([0-9a-f]+)\.\.\.([0-9a-f]+)", path):
            return httpx.Response(200, json={"status": "ahead" if m.group(1) in self.deployed_contains else "diverged"})
        raise AssertionError(f"endpoint inesperado: {path}")


class FakeAI:
    """Anthropic client stand-in: returns the configured tool output and records what was sent."""

    def __init__(self, items=None, overview="Semana com entregas e pendências.", fail=None):
        self.items, self.overview, self.fail, self.sent = items, overview, fail, []
        self.messages = self

    def count_tokens(self, **kwargs):
        return SimpleNamespace(input_tokens=1000)

    def create(self, **kwargs):
        if self.fail:
            raise self.fail
        payload = json.loads(kwargs["messages"][0]["content"])
        self.sent.append(payload)
        items = self.items(payload["items"]) if callable(self.items) else (self.items or [])
        block = SimpleNamespace(type="tool_use", name="entregar_pauta", input={"overview": self.overview, "items": items})
        return SimpleNamespace(content=[block], stop_reason="tool_use", usage=SimpleNamespace(input_tokens=1000, output_tokens=200), model="m")


@pytest.fixture
def github():
    return FakeGitHub()


@pytest.fixture
def app_settings():
    return Settings(_env_file=None, github_token=SecretStr(TOKEN), github_repository="Arthur-A-C/PRM", deployed_commit=DEPLOYED,
                    meeting_ai_model="claude-test-model")


TABLES = (Organization, User, Meeting, TranscriptRevision, MeetingRun, Activity, ActivityAudit, WeeklyAgenda, WeeklyAgendaRevision, WeeklyAgendaSettings)


@pytest.fixture
def world():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    for model in TABLES:
        model.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as db:
        org, other = Organization(name="PRM"), Organization(name="Outra")
        db.add_all([org, other]); db.flush()
        users = {key: User(name=name, email=f"{key}@x.test", role=role, organization_id=(other if key == "fora" else org).id, password_hash="x", active=True)
                 for key, name, role in [("kaue", "Kauê", "desenvolvedor"), ("arthur", "Arthur", "gestor"), ("daniel", "Daniel", "gestor"),
                                         ("vera", "Vera", "vendedor"), ("fora", "Fora", "desenvolvedor")]}
        db.add_all(users.values()); db.flush()
        meeting = Meeting(organization_id=org.id, creator_id=users["kaue"].id, title="Reunião de desenvolvimento PRM", partner="", opportunity="",
                          timezone="America/Sao_Paulo", metadata_confirmed={}, participants=[])
        sales = Meeting(organization_id=org.id, creator_id=users["kaue"].id, title="Visita comercial", partner="Cliente X", opportunity="",
                        timezone="America/Sao_Paulo", metadata_confirmed={}, participants=[])
        db.add_all([meeting, sales]); db.flush()
        run = MeetingRun(organization_id=org.id, meeting_id=meeting.id, stage="analysis", key="k1", context={})
        run2 = MeetingRun(organization_id=org.id, meeting_id=sales.id, stage="analysis", key="k2", context={})
        db.add_all([run, run2]); db.flush()
        tasks = {}

        def task(key, title, status, *, approval="published", due=None, completed=None, assignee="daniel", m=meeting, r=run, details=None):
            tasks[key] = Activity(organization_id=org.id, meeting_id=m.id, analysis_run_id=r.id, proposal_local_id=key, creator_id=users["kaue"].id,
                                  assignee_user_id=users[assignee].id if assignee else None, kind="task", title=title, description="",
                                  approval=approval, status=status, due_date=due, completed_at=completed, timezone="America/Sao_Paulo",
                                  details=details or {})
            db.add(tasks[key])

        task("done", "Testar pauta com a equipe", "done", completed=datetime(2026, 10, 21, 15, tzinfo=SP))
        task("blocked", "Configurar TLS no gateway", "blocked", due=date(2026, 10, 24), assignee="arthur")
        task("overdue", "Revisar documentação de deploy", "todo", due=date(2026, 10, 16))
        task("next", "Validar checklist da Portwell", "todo", due=date(2026, 10, 27), assignee="kaue")
        task("progress", "Ajustar layout do Planner", "in_progress", due=date(2026, 11, 20))
        task("cancelled", "Tarefa cancelada", "cancelled", due=date(2026, 10, 22))
        task("draft", "Proposta não aprovada", "todo", approval="draft", due=date(2026, 10, 22))
        task("simulation", "Card de demonstração", "todo", due=date(2026, 10, 22), details={"simulation": True})
        task("old_done", "Concluída na semana passada", "done", completed=datetime(2026, 10, 14, 15, tzinfo=SP))
        task("sales", "Enviar proposta ao Cliente X", "in_progress", m=sales, r=run2, due=date(2026, 10, 22))
        db.commit()
        yield SimpleNamespace(engine=engine, org=org, other=other, users=users, tasks=tasks, session=lambda: Session(engine, expire_on_commit=False))
    engine.dispose()


def generate(world, app_settings, github, *, ai=None, actor="kaue", **kwargs):
    with world.session() as db:
        agenda = agendas.generate(db, world.org.id, world.users[actor].id if actor else None, app_settings, monday=MONDAY, now=NOW,
                                  transport=httpx.MockTransport(github.handle), ai_client=ai or FakeAI(fail=RuntimeError("sem IA nos testes")), **kwargs)
        db.commit()
        return agenda


def by_key(agenda):
    return {i["key"]: i for i in agenda.items}


# --- Semana e fuso -------------------------------------------------------------------------------

def test_week_is_monday_to_friday_in_sao_paulo():
    assert agendas.week_of(date(2026, 10, 23)) == (MONDAY, date(2026, 10, 23))
    saturday_night = datetime(2026, 10, 25, 1, tzinfo=timezone.utc)  # Saturday 22:00 in São Paulo
    assert agendas.current_week(saturday_night)[0] == MONDAY
    friday_late = datetime(2026, 10, 24, 2, 30, tzinfo=timezone.utc)  # Friday 23:30 in São Paulo, already Saturday in UTC
    assert agendas.current_week(friday_late)[0] == MONDAY
    start, end = agendas.bounds(MONDAY)
    assert start.isoformat() == "2026-10-19T03:00:00+00:00" and end.isoformat() == "2026-10-24T03:00:00+00:00"


# --- Cliente GitHub ------------------------------------------------------------------------------

def test_github_client_reads_only_allowed_metadata(github):
    client = gh.GitHubClient(TOKEN, "Arthur-A-C/PRM", transport=httpx.MockTransport(github.handle))
    for path in ("/contents/app/config.py", "/git/trees/main", "/actions/secrets", "/pulls/3/files", "/../../user"):
        with pytest.raises(gh.GitHubError, match="não permitido"):
            client.get(path)
    data, _ = client.get("")
    assert data["private"] and client.scopes == ["repo", "workflow"]
    assert github.headers[0]["authorization"] == f"Bearer {TOKEN}"
    with pytest.raises(gh.GitHubError, match="não configurada"):
        gh.GitHubClient("", "Arthur-A-C/PRM")
    with pytest.raises(gh.GitHubError, match="inválido"):
        gh.GitHubClient(TOKEN, "Arthur-A-C/PRM/../x")
    with pytest.raises(gh.GitHubError, match="HTTPS"):
        gh.GitHubClient(TOKEN, "Arthur-A-C/PRM", api_url="http://api.github.com")


@pytest.mark.parametrize("status,headers,message", [(401, {}, "inválido ou expirado"), (403, {"x-ratelimit-remaining": "0"}, "Limite"),
                                                    (403, {}, "permissão de leitura"), (404, {}, "não encontrado"), (302, {"location": "https://evil"}, "HTTP 302")])
def test_github_errors_are_readable_and_never_leak_the_token(github, status, headers, message):
    github.fail = lambda request: httpx.Response(status, headers=headers, json={"message": "Bad credentials " + TOKEN})
    client = gh.GitHubClient(TOKEN, "Arthur-A-C/PRM", transport=httpx.MockTransport(github.handle))
    with pytest.raises(gh.GitHubError, match=message) as error:
        client.get("")
    assert TOKEN not in str(error.value) and "evil" not in str(error.value)


# --- Classificação rigorosa ------------------------------------------------------------------------

def test_items_follow_the_status_ladder(world, app_settings, github):
    agenda = generate(world, app_settings, github)
    items = by_key(agenda)
    assert items["pr:1"]["section"] == "deployed" and items["pr:1"]["status"] == "deployed"
    assert items["pr:2"]["section"] == "bugs" and items["pr:2"]["status"] == "merged" and "implantação não confirmada" in items["pr:2"]["text"]
    assert items["pr:3"]["section"] == "review" and items["pr:3"]["status"] == "pr_open"
    assert items["pr:4"]["section"] == "review" and items["pr:5"]["section"] == "closed" and items["pr:6"]["section"] == "review"
    assert "pr:7" not in items  # merged before the week
    assert items["ci:pr:3"]["status"] == "ci_ok" and items["ci:pr:3"]["section"] == "tests" and "não indica implantação" in items["ci:pr:3"]["text"]
    assert items["ci:pr:4"]["status"] == "ci_fail" and "decision:ci:pr:4" in items
    assert "decision:review:pr:4" in items and "decision:review:pr:3" not in items  # #3 has a reviewer and is recent
    assert items["decision:deploy"]["section"] == "decisions" and "PR #2" in items["decision:deploy"]["text"] and "PR #1" not in items["decision:deploy"]["text"]
    assert items["branch:feature/rascunho"]["status"] == "branch" and "pauta semanal" in items["branch:feature/rascunho"]["text"]
    assert "branch:feature/3" not in items  # commit belongs to PR #3: no duplicate
    direct = items["main:2026-10-19"]
    assert direct["status"] == "merged" and "Merge PR #1" not in direct["text"]  # the merge commit is represented by PR #1
    assert items["issue:10"]["section"] == "pending" and items["issue:11"]["section"] == "bugs" and items["issue:11"]["status"] == "issue_closed"
    assert items["issue:12"]["section"] == "next_week" and "decision:issue:12" in items and items["issue:13"]["section"] == "issues_closed"
    assert "issue:3" not in items  # pull requests listed by the issues endpoint are ignored
    keys = [i["key"] for i in agenda.items]
    assert len(keys) == len(set(keys))
    # Nothing that is not deployed may say so.
    for item in agenda.items:
        if item["status"] != "deployed":
            assert not re.search(r"\bimplantad[oa]\b", item["text"]) or "não" in item["text"] or "Integração" in item["text"]


def test_without_deployed_commit_nothing_is_deployed(world, github):
    settings = Settings(_env_file=None, github_token=SecretStr(TOKEN), deployed_commit="")
    agenda = generate(world, settings, github)
    assert not [i for i in agenda.items if i["status"] == "deployed"]
    assert by_key(agenda)["pr:1"]["section"] == "merged" and "commit em produção não informado" in by_key(agenda)["pr:1"]["text"]
    assert any("PRM_DEPLOYED_COMMIT" in w for w in agenda.generation["warnings"])
    assert not [p for p in github.paths if "/compare/" in p]


def test_planner_buckets_and_exclusions(world, app_settings, github):
    items = by_key(generate(world, app_settings, github))
    t = {k: str(v.id) for k, v in world.tasks.items()}
    assert items[f"task:{t['done']}"]["section"] == "planner_done" and items[f"task:{t['done']}"]["people"] == ["Daniel"]
    assert items[f"task:{t['blocked']}"]["status"] == "task_blocked" and f"decision:task:{t['blocked']}" in items
    assert items[f"task:{t['overdue']}"]["status"] == "task_overdue" and items[f"task:{t['next']}"]["section"] == "next_week"
    assert items[f"task:{t['progress']}"]["section"] == "planner_progress"
    for excluded in ("cancelled", "draft", "simulation", "old_done"):
        assert f"task:{t[excluded]}" not in items
    assert items[f"task:{t['done']}"]["links"] == [{"label": "Card no PRM", "url": f"/cards?activity={t['done']}"}]


def test_planner_filter_limits_tasks(world, app_settings, github):
    with world.session() as db:
        agendas.settings_for(db, world.org.id).planner_filter = "desenvolvimento"
        db.commit()
    items = by_key(generate(world, app_settings, github))
    assert f"task:{world.tasks['sales'].id}" not in items and f"task:{world.tasks['done'].id}" in items


def test_contributions_only_from_evidence(world, app_settings, github):
    with world.session() as db:
        agendas.settings_for(db, world.org.id).people = {"Kaue-Borges": "Kauê", "arthur-dev": "Arthur"}
        db.commit()
    agenda = generate(world, app_settings, github)
    people = {c["person"]: c["counts"] for c in agenda.generation["contributions"]}
    assert people["Kauê"]["deployed"] == 1 and people["Arthur"]["pr_open"] == 1 and people["daniel-dev"]["branch"] == 1
    assert "Daniel" in people  # Planner assignee


# --- Redação por IA, com verificação ----------------------------------------------------------------

def test_ai_wording_is_checked_against_the_evidence(world, app_settings, github):
    def reply(sent):
        texts = []
        for item in sent:
            if item["key"] == "pr:2":
                texts.append({"key": "pr:2", "text": "PR #2 corrigiu o caminho da imagem e já está implantado em produção."})  # false claim
            elif item["key"] == "pr:3":
                texts.append({"key": "pr:3", "text": "PR #3 traz a seleção de pastas e aguarda revisão de Arthur."})
            elif item["key"] == "pr:5":
                texts.append({"key": "pr:5", "text": "PR #5 foi substituído pelo PR #99."})  # invented number
            elif item["key"] == "pr:1":
                texts.append({"key": "pr:1", "text": "PR #1 com a infraestrutura Docker está implantado."})  # true: deployed
        return texts + [{"key": "pr:404", "text": "Item inventado."}]
    ai = FakeAI(reply)
    agenda = generate(world, app_settings, github, ai=ai)
    items = by_key(agenda)
    assert items["pr:3"]["wording"] == "ai" and items["pr:3"]["text"].startswith("PR #3 traz")
    assert items["pr:1"]["wording"] == "ai"
    assert items["pr:2"]["wording"] == "rules" and "implantação não confirmada" in items["pr:2"]["text"]
    assert items["pr:5"]["wording"] == "rules" and "pr:404" not in items
    assert agenda.generation["ai"]["used"] and agenda.generation["ai"]["rejected"] == 2
    sent = json.dumps(ai.sent)
    assert TOKEN not in sent and "corpo longo" not in sent  # redacted commit text and only the first line are sent


def test_ai_overview_cannot_claim_deployment_without_proof(world, github):
    settings = Settings(_env_file=None, github_token=SecretStr(TOKEN), deployed_commit="", meeting_ai_model="m")
    agenda = generate(world, settings, github, ai=FakeAI([], overview="Tudo foi implantado em produção nesta semana."))
    assert "implantado em produção" not in agenda.overview and agenda.overview.startswith("Semana de 19/10")


@pytest.mark.parametrize("case", ["outage", "disabled", "not_configured"])
def test_agenda_works_without_ai(world, app_settings, github, case):
    ai = FakeAI(fail=RuntimeError("503 overloaded"))
    if case == "disabled":
        with world.session() as db:
            agendas.settings_for(db, world.org.id).ai_enabled = False
            db.commit()
    if case == "not_configured":
        app_settings = Settings(_env_file=None, github_token=SecretStr(TOKEN), deployed_commit=DEPLOYED, meeting_ai_model="")
    agenda = generate(world, app_settings, github, ai=ai)
    assert not agenda.generation["ai"]["used"] and agenda.generation["ai"]["reason"]
    assert all(i["wording"] == "rules" for i in agenda.items) and len(agenda.items) > 20
    if case == "disabled":
        assert not ai.sent


def test_github_outage_still_produces_the_planner_agenda(world, app_settings, github):
    github.fail = lambda request: httpx.Response(401, json={})
    agenda = generate(world, app_settings, github)
    assert agenda.generation["github_error"].startswith("Token do GitHub inválido")
    assert {i["origin"] for i in agenda.items} == {"planner"} and TOKEN not in json.dumps(agenda.sources)


def test_secrets_in_commit_messages_are_redacted(world, app_settings, github):
    agenda = generate(world, app_settings, github)
    dump = json.dumps({"items": agenda.items, "sources": agenda.sources, "search": agenda.search_text})
    assert TOKEN not in dump and "[removido]" in dump
    fake_url, fake_key = "https://user:" + "senha" + "123@host/x", "sk-" + "ant-" + "abcdef1234567890"  # built at runtime: not real secrets
    assert agendas.redact(f"url {fake_url} e {fake_key}") == "url https://[removido]@host/x e [removido]"


# --- Edições humanas, regeneração e deduplicação -----------------------------------------------------

def test_regeneration_preserves_human_edits_and_flags_status_changes(world, app_settings, github):
    agenda = generate(world, app_settings, github)
    with world.session() as db:
        agenda = agendas.get_agenda(db, world.org.id, agenda.id, lock=True)
        agenda = agendas.edit_item(db, agenda, world.users["arthur"].id, "pr:3", agenda.version, text="Seleção de pastas: revisar na reunião.")
        agenda = agendas.edit_item(db, agenda, world.users["arthur"].id, "pr:6", agenda.version, hidden=True)
        agenda = agendas.edit_item(db, agenda, world.users["arthur"].id, "issue:13", agenda.version, text="Ideia descartada; registrar motivo.")
        agenda = agendas.add_manual(db, agenda, world.users["daniel"].id, agenda.version, "decision", "Implantar PR #2 na segunda.")
        agenda = agendas.set_overview(db, agenda, world.users["arthur"].id, agenda.version, "Resumo combinado na reunião.")
        db.commit()
        version = agenda.version
    github.pulls[2] = pr(3, "Seleção de pastas do computador", state="closed", merged=at(23, 9), created=at(22))  # PR #3 merged meanwhile
    github.issues = [i for i in github.issues if i["number"] != 13]  # evidence disappears
    again = generate(world, app_settings, github, expected_version=version)
    items = by_key(again)
    assert items["pr:3"]["text"] == "Seleção de pastas: revisar na reunião." and items["pr:3"]["edited"]
    assert items["pr:3"]["status"] == "merged" and "PR aberto" in items["pr:3"]["source_changed"]
    assert items["pr:6"]["hidden"] and items["issue:13"]["source_missing"]
    assert again.manual[0]["text"] == "Implantar PR #2 na segunda." and again.overview == "Resumo combinado na reunião."
    keys = [i["key"] for i in again.items]
    assert len(keys) == len(set(keys))
    with world.session() as db:
        again = agendas.get_agenda(db, world.org.id, again.id, lock=True)
        restored = agendas.edit_item(db, again, world.users["arthur"].id, "pr:3", again.version, restore=True)
        assert not by_key(restored)["pr:3"]["edited"] and "source_changed" not in by_key(restored)["pr:3"]
        db.commit()


def test_concurrent_edits_are_refused(world, app_settings, github):
    agenda = generate(world, app_settings, github)
    with world.session() as db:
        stale = agenda.version
        current = agendas.get_agenda(db, world.org.id, agenda.id, lock=True)
        agendas.edit_item(db, current, world.users["arthur"].id, "pr:3", stale, text="Primeira edição")
        db.commit()
        with pytest.raises(agendas.AgendaError, match="alterada por outra pessoa"):
            agendas.edit_item(db, current, world.users["daniel"].id, "pr:3", stale, text="Edição perdida")
        with pytest.raises(agendas.AgendaError, match="alterada por outra pessoa"):
            agendas.generate(db, world.org.id, world.users["daniel"].id, app_settings, monday=MONDAY, now=NOW,
                             transport=httpx.MockTransport(github.handle), ai_client=FakeAI(fail=RuntimeError()), expected_version=stale)


def test_lifecycle_and_audit(world, app_settings, github):
    agenda = generate(world, app_settings, github)
    kaue, arthur = world.users["kaue"].id, world.users["arthur"].id
    with world.session() as db:
        agenda = agendas.get_agenda(db, world.org.id, agenda.id, lock=True)
        agenda = agendas.transition(db, agenda, arthur, agenda.version, "approve")
        assert agenda.status == "approved" and agenda.approved_by_id == arthur
        with pytest.raises(agendas.AgendaError, match="Somente rascunhos"):
            agendas.add_manual(db, agenda, kaue, agenda.version, "note", "x")
        with pytest.raises(agendas.AgendaError, match="aprovada"):
            agendas.generate(db, world.org.id, kaue, app_settings, monday=MONDAY, now=NOW, transport=httpx.MockTransport(github.handle))
        agenda = agendas.transition(db, agenda, kaue, agenda.version, "archive")
        with pytest.raises(agendas.AgendaError, match="arquivada"):
            agendas.generate(db, world.org.id, kaue, app_settings, monday=MONDAY, now=NOW, transport=httpx.MockTransport(github.handle),
                             expected_version=agenda.version)
        with pytest.raises(agendas.AgendaError, match="indisponível"):
            agendas.transition(db, agenda, kaue, agenda.version, "approve")
        agenda = agendas.transition(db, agenda, kaue, agenda.version, "unarchive")
        assert agenda.status == "draft" and agenda.archived_at is None
        db.commit()
        actions = [r.action for r in db.scalars(select(WeeklyAgendaRevision).where(WeeklyAgendaRevision.agenda_id == agenda.id)
                                                 .order_by(WeeklyAgendaRevision.created_at))]
    assert actions == ["generated", "approve", "archive", "unarchive"]


def test_regenerating_an_approved_agenda_returns_it_to_draft(world, app_settings, github):
    agenda = generate(world, app_settings, github)
    with world.session() as db:
        agenda = agendas.transition(db, agendas.get_agenda(db, world.org.id, agenda.id, lock=True), world.users["arthur"].id, agenda.version, "approve")
        db.commit()
    again = generate(world, app_settings, github, expected_version=agenda.version)
    assert again.status == "draft" and again.approved_at is None


def test_history_search(world, app_settings, github):
    agenda = generate(world, app_settings, github)
    with world.session() as db:
        agendas.add_manual(db, agendas.get_agenda(db, world.org.id, agenda.id, lock=True), world.users["kaue"].id, agenda.version, "subject",
                           "Planejar homologação na Portwell")
        db.commit()
        assert [a.id for a in agendas.history(db, world.org.id, "portwell")[0]] == [agenda.id]
        assert [a.id for a in agendas.history(db, world.org.id, "seleção de pastas")[0]] == [agenda.id]
        assert agendas.history(db, world.org.id, "inexistente")[0] == []
        assert agendas.history(db, world.other.id, "portwell")[0] == []  # other organization
        assert agendas.history(db, world.org.id, status="approved")[0] == []


# --- Agendamento ----------------------------------------------------------------------------------

def test_scheduled_draft_runs_once_after_the_configured_time(world, app_settings, github):
    with world.session() as db:
        agendas.settings_for(db, world.org.id).draft_time = "09:30"
        db.commit()
    run = lambda now: agendas.scheduled_drafts(world.engine, app_settings, now=now, transport=httpx.MockTransport(github.handle),
                                               ai_client=FakeAI(fail=RuntimeError()))
    assert run(datetime(2026, 10, 23, 9, 0, tzinfo=SP)) == 0  # before time
    assert run(datetime(2026, 10, 22, 10, 0, tzinfo=SP)) == 0  # Thursday
    assert run(datetime(2026, 10, 23, 9, 31, tzinfo=SP)) == 1
    assert run(datetime(2026, 10, 23, 15, 0, tzinfo=SP)) == 0  # same day: not regenerated over the morning work
    with world.session() as db:
        agenda = db.scalar(select(WeeklyAgenda))
        assert agenda.generated_by_id is None and agenda.generation["scheduled_for"] == "2026-10-23"
        agendas.transition(db, agendas.get_agenda(db, world.org.id, agenda.id, lock=True), world.users["arthur"].id, agenda.version, "approve")
        db.commit()
    assert run(datetime(2026, 10, 30, 9, 31, tzinfo=SP)) == 1  # next Friday: next week
    with world.session() as db:
        assert [a.week_start for a in db.scalars(select(WeeklyAgenda).order_by(WeeklyAgenda.week_start))] == [MONDAY, MONDAY + timedelta(days=7)]
        agendas.settings_for(db, world.org.id).enabled = False
        db.commit()
    assert run(datetime(2026, 11, 6, 9, 31, tzinfo=SP)) == 0


def test_scheduled_failure_is_recorded_without_stopping(world, app_settings, github, monkeypatch):
    monkeypatch.setattr(agendas, "planner_activities", lambda *a, **k: (_ for _ in ()).throw(ValueError("Planner indisponível")))
    with world.session() as db:
        agendas.settings_for(db, world.org.id)
        db.commit()
    assert agendas.scheduled_drafts(world.engine, app_settings, now=datetime(2026, 10, 23, 9, 0, tzinfo=SP),
                                    transport=httpx.MockTransport(github.handle)) == 0
    with world.session() as db:
        failure = db.scalar(select(WeeklyAgendaRevision).where(WeeklyAgendaRevision.action == "scheduled_failed"))
        assert failure.changes["error"] == "Planner indisponível"


def test_worker_hook_never_breaks_the_alerts_loop(monkeypatch, capsys):
    import importlib.util
    path = Path(__file__).parents[1] / "scripts/meeting_worker.py"
    spec = importlib.util.spec_from_file_location("meeting_worker_script", path); module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    monkeypatch.setattr(module, "inspect", lambda engine: (_ for _ in ()).throw(RuntimeError("db down")))
    module.weekly_agenda_drafts(object(), object())
    assert "Pauta semanal: RuntimeError" in capsys.readouterr().out


# --- PDF ---------------------------------------------------------------------------------------------

def test_pdf_export(world, app_settings, github):
    from pypdf import PdfReader
    from app.services.weekly_agenda_pdf import render
    agenda = generate(world, app_settings, github)
    with world.session() as db:
        agenda = agendas.get_agenda(db, world.org.id, agenda.id, lock=True)
        agenda = agendas.edit_item(db, agenda, world.users["arthur"].id, "pr:6", agenda.version, hidden=True)
        agenda = agendas.add_manual(db, agenda, world.users["daniel"].id, agenda.version, "decision", "Implantar na segunda-feira.")
        db.commit()
    content = render(agenda, {str(u.id): u.name for u in world.users.values()}, base_url="https://prm.local/")
    assert content.startswith(b"%PDF")
    text = " ".join(page.extract_text() for page in PdfReader(io.BytesIO(content)).pages)
    assert "Integrado na main" in text and "Implantar na segunda-feira." in text and "Daniel" in text
    assert "Refatoração antiga" not in text and TOKEN not in text


# --- API, permissões e interface ------------------------------------------------------------------------

@pytest.fixture
def api(world, app_settings, github, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.config import get_settings
    from app.db import get_db_session
    from app.dependencies import get_current_auth
    from app.routers import weekly_agenda as router
    from app.services.security import hash_secret
    app = FastAPI(); app.include_router(router.router)
    state = SimpleNamespace(user=world.users["kaue"])
    session = world.session()
    app.dependency_overrides[get_current_auth] = lambda: SimpleNamespace(user=state.user, login_session=SimpleNamespace(csrf_hash=hash_secret("csrf")))
    app.dependency_overrides[get_db_session] = lambda: session
    app.dependency_overrides[get_settings] = lambda: app_settings
    monkeypatch.setattr(router, "github_transport", httpx.MockTransport(github.handle))
    monkeypatch.setattr(router, "ai_client", FakeAI(fail=RuntimeError("sem IA")))
    monkeypatch.setattr(agendas, "current_week", lambda now=None: (MONDAY, MONDAY + timedelta(days=4)))
    yield SimpleNamespace(client=TestClient(app), state=state, users=world.users)
    session.close()


H = {"X-CSRF-Token": "csrf"}


def test_api_flow(api):
    c = api.client
    config = c.get("/api/v1/pauta-semanal/configuracao").json()
    assert config["weekday"] == 4 and config["integration"]["github_configured"] and config["integration"]["deployed_commit"] == DEPLOYED
    assert c.put("/api/v1/pauta-semanal/configuracao", json={**{k: config[k] for k in ("enabled", "weekday", "ai_enabled", "planner_filter", "people")},
                                                            "draft_time": "25:00"}, headers=H).status_code == 422
    saved = c.put("/api/v1/pauta-semanal/configuracao", json={"enabled": True, "weekday": 4, "draft_time": "07:45", "ai_enabled": False,
                                                              "planner_filter": "", "people": {"Kaue-Borges": "Kauê"}}, headers=H)
    assert saved.json()["draft_time"] == "07:45"
    test = c.post("/api/v1/pauta-semanal/configuracao/teste", headers=H).json()
    assert test["ok"] and "escopos amplos" in test["message"]
    assert c.post("/api/v1/pauta-semanal/pautas", json={"semana": "2026-10-21"}).status_code == 403  # CSRF
    agenda = c.post("/api/v1/pauta-semanal/pautas", json={"semana": "2026-10-21"}, headers=H).json()
    assert agenda["week_start"] == "2026-10-19" and agenda["status"] == "draft" and agenda["generated_by"] == "Kauê"
    sections = {s["key"]: s for s in agenda["sections"]}
    assert [i["key"] for i in sections["deployed"]["items"]] == ["pr:1"] and sections["deployed"]["items"][0]["people"] == ["Kauê"]
    url = f"/api/v1/pauta-semanal/pautas/{agenda['id']}"
    api.state.user = api.users["arthur"]
    edited = c.patch(url + "/itens/pr:3", json={"version": agenda["version"], "text": "Revisar na reunião."}, headers=H).json()
    assert next(i for s in edited["sections"] for i in s["items"] if i["key"] == "pr:3")["edited_by"] == "Arthur"
    assert c.patch(url + "/itens/pr:3", json={"version": agenda["version"], "text": "x"}, headers=H).status_code == 422  # stale version
    noted = c.post(url + "/anotacoes", json={"version": edited["version"], "kind": "decision", "text": "Implantar PR #2."}, headers=H).json()
    assert noted["manual"][0]["author"] == "Arthur" and noted["manual"][0]["kind_label"] == "Decisão registrada"
    approved = c.post(url + "/aprovar", json={"version": noted["version"]}, headers=H).json()
    assert approved["status"] == "approved" and approved["approved_by"] == "Arthur"
    assert c.post(url + "/anotacoes", json={"version": approved["version"], "kind": "note", "text": "x"}, headers=H).status_code == 422
    pdf = c.get(url + "/pdf")
    assert pdf.headers["content-type"] == "application/pdf" and pdf.content.startswith(b"%PDF")
    found = c.get("/api/v1/pauta-semanal/pautas", params={"q": "implantar pr #2"}).json()
    assert [a["id"] for a in found["items"]] == [agenda["id"]] and found["items"][0]["counts"]["review"] >= 2
    assert c.get("/api/v1/pauta-semanal/pautas/atual").json()["agenda"]["id"] == agenda["id"]
    history = c.get(url + "/historico").json()["items"]
    assert [h["action"] for h in history][:4] == ["exported_pdf", "approve", "manual_added", "item_edited"]
    assert history[-1]["actor"] == "Kauê"
    for response in (config, test, agenda, edited, approved, found, history):
        assert TOKEN not in json.dumps(response)


def test_api_permissions(api, world):
    c = api.client
    agenda = c.post("/api/v1/pauta-semanal/pautas", json={}, headers=H).json()
    api.state.user = api.users["vera"]  # vendedor
    assert c.get("/api/v1/pauta-semanal/pautas").status_code == 403
    assert c.get(f"/api/v1/pauta-semanal/pautas/{agenda['id']}").status_code == 403
    api.state.user = api.users["fora"]  # other organization
    assert c.get(f"/api/v1/pauta-semanal/pautas/{agenda['id']}").status_code == 404
    assert c.get("/api/v1/pauta-semanal/pautas").json()["items"] == []
    assert c.get(f"/api/v1/pauta-semanal/pautas/{agenda['id']}/pdf").status_code == 404


def test_api_requires_migration():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.db import get_db_session
    from app.dependencies import get_current_auth
    from app.routers import weekly_agenda as router
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    app = FastAPI(); app.include_router(router.router)
    app.dependency_overrides[get_db_session] = lambda: Session(engine)
    app.dependency_overrides[get_current_auth] = lambda: SimpleNamespace(user=SimpleNamespace(role="gestor"))
    response = TestClient(app).get("/api/v1/pauta-semanal/pautas")
    assert response.status_code == 503 and "migração" in response.json()["detail"]


def test_pages():
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    from test_operations_workspace import Elements, render
    html = render("Pauta Semanal")
    ids = [a["id"] for _, a in Elements(html).nodes if "id" in a]
    assert len(ids) == len(set(ids))
    assert {"wa-page", "wa-week", "wa-generate", "wa-agenda", "wa-sections", "wa-manual-form", "wa-history", "wa-settings", "wa-pdf", "wa-audit"} <= set(ids)
    assert "/js/weekly-agenda.js" in html and "/css/weekly-agenda.css" in html and "/js/weekly-agenda.js" not in render("Reuniões")
    env = Environment(loader=FileSystemLoader("app/templates"), autoescape=select_autoescape(["html"]))
    page = lambda role: env.get_template("_meeting_pages.html").render(title="Reuniões", user={"role": role})
    assert "/reunioes/pauta-semanal" in page("gestor") and "/reunioes/pauta-semanal" not in page("vendedor")
    from app.routers import pages
    import inspect
    source = inspect.getsource(pages)
    assert 'route_titles["reunioes/pauta-semanal"] = "Pauta Semanal"' in source and '"Remoção de Arquivos", "Pauta Semanal"}' in source


def test_migration_chain():
    import importlib.util
    path = Path(__file__).parents[1] / "migrations/versions/20261023_0013_weekly_agenda.py"
    spec = importlib.util.spec_from_file_location("m0013", path); module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    assert module.down_revision == "20261021_0011"
    assert [t.name for t in module.WEEKLY_AGENDA_TABLES] == ["weekly_agendas", "weekly_agenda_revisions", "weekly_agenda_settings"]
