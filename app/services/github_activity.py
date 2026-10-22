"""Read-only GitHub metadata for the Pauta Semanal: commits, pull requests, issues, CI results and deployment proof.

Only an allowlist of metadata endpoints is reachable: no file contents, diffs, patches, secrets or write
methods. The token lives in the backend (PRM_GITHUB_TOKEN) and never appears in results, errors or logs.
Recommended token: fine-grained, repository Arthur-A-C/PRM only, read-only Metadata, Contents (commit
listing), Pull requests, Issues, Checks/Commit statuses.
"""
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx

REPOSITORY = re.compile(r"[A-Za-z0-9-]{1,39}/[A-Za-z0-9._-]{1,100}")
SHA = re.compile(r"[0-9a-f]{7,40}")
# Metadata endpoints only (relative to /repos/{owner}/{repo}).
ALLOWED = re.compile(r"(?:|/commits|/commits/[0-9a-f]{7,40}/check-runs|/branches|/pulls|/pulls/\d+/commits|/issues|"
                     r"/compare/[0-9a-f]{7,40}\.\.\.[0-9a-f]{7,40})")
MAX_PAGES = 5
MAX_BRANCHES = 30
MAX_DETAIL = 30  # per-PR follow-up calls (commits, checks, deployment proof)
BUG_LABELS = {"bug", "fix", "bugfix", "defeito", "erro", "correção", "correcao", "hotfix"}
BUG_TITLE = re.compile(r"^\s*(fix|bugfix|hotfix|corrige|correção|correcao)\b|\bfix\(", re.IGNORECASE)
DECISION_LABELS = {"decision", "decisão", "decisao", "needs-decision", "question", "pergunta", "discussão", "discussao"}


class GitHubError(ValueError):
    """Readable, token-free failure."""


def parse_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


class GitHubClient:
    def __init__(self, token, repository, api_url="https://api.github.com", timeout=20, transport=None):
        if not token:
            raise GitHubError("Integração GitHub não configurada (PRM_GITHUB_TOKEN no backend).")
        if not REPOSITORY.fullmatch(repository or ""):
            raise GitHubError("Repositório GitHub inválido; use dono/nome.")
        parts = urlsplit(api_url)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
            raise GitHubError("URL da API do GitHub deve ser HTTPS.")
        self.repository = repository
        self.scopes = None
        self.client = httpx.Client(base_url=api_url.rstrip("/"), timeout=httpx.Timeout(timeout, connect=10), follow_redirects=False,
                                   trust_env=False, transport=transport,
                                   headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                                            "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "PRM-Pauta-Semanal/1"})
        self.calls = 0

    def close(self):
        self.client.close()

    def get(self, path, params=None):
        """One allowed metadata GET; returns (json, response)."""
        if not ALLOWED.fullmatch(path):
            raise GitHubError("Endpoint do GitHub não permitido para a pauta.")
        self.calls += 1
        try:
            response = self.client.get(f"/repos/{self.repository}{path}", params=params or {})
        except httpx.TimeoutException:
            raise GitHubError("Tempo limite excedido ao consultar o GitHub.") from None
        except httpx.HTTPError:
            raise GitHubError("Falha de comunicação com o GitHub.") from None
        if "x-oauth-scopes" in response.headers and self.scopes is None:
            self.scopes = sorted(s.strip() for s in response.headers["x-oauth-scopes"].split(",") if s.strip())
        if response.status_code == 401:
            raise GitHubError("Token do GitHub inválido ou expirado (401).")
        if response.status_code in {403, 429} and response.headers.get("x-ratelimit-remaining") == "0":
            raise GitHubError("Limite de requisições do GitHub atingido; tente mais tarde.")
        if response.status_code == 403:
            raise GitHubError("Acesso negado pelo GitHub (403): o token não tem a permissão de leitura necessária.")
        if response.status_code == 404:
            raise GitHubError("Repositório ou recurso não encontrado (404): confira o repositório e o acesso do token.")
        if response.status_code != 200:
            raise GitHubError(f"GitHub respondeu HTTP {response.status_code}.")
        try:
            return response.json(), response
        except ValueError:
            raise GitHubError("Resposta inválida do GitHub.") from None

    def pages(self, path, params, stop=None):
        """Follows Link pagination (bounded); ``stop(item)`` ends early on sorted listings."""
        params = {**params, "per_page": 100, "page": 1}
        results = []
        for _ in range(MAX_PAGES):
            data, response = self.get(path, params)
            if not isinstance(data, list):
                raise GitHubError("Resposta inesperada do GitHub.")
            for item in data:
                if stop and stop(item):
                    return results, False
                results.append(item)
            if 'rel="next"' not in response.headers.get("link", ""):
                return results, False
            params["page"] += 1
        return results, True


def _pr(row):
    return {"number": row["number"], "title": row.get("title") or "", "state": row.get("state"), "draft": bool(row.get("draft")),
            "author": (row.get("user") or {}).get("login"), "assignees": [a.get("login") for a in row.get("assignees") or []],
            "reviewers": [r.get("login") for r in row.get("requested_reviewers") or []],
            "labels": [l.get("name", "") for l in row.get("labels") or []], "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"), "closed_at": row.get("closed_at"), "merged_at": row.get("merged_at"),
            "url": row.get("html_url"), "head": (row.get("head") or {}).get("ref"), "head_sha": (row.get("head") or {}).get("sha"),
            "base": (row.get("base") or {}).get("ref"), "merge_commit_sha": row.get("merge_commit_sha")}


def _commit(row, branch):
    commit = row.get("commit") or {}
    return {"sha": row.get("sha"), "message": (commit.get("message") or "").split("\n")[0][:240],
            "author": (row.get("author") or {}).get("login") or (commit.get("author") or {}).get("name"),
            "date": (commit.get("author") or {}).get("date"), "url": row.get("html_url"), "branches": [branch]}


def _issue(row):
    return {"number": row["number"], "title": row.get("title") or "", "state": row.get("state"), "state_reason": row.get("state_reason"),
            "author": (row.get("user") or {}).get("login"), "assignees": [a.get("login") for a in row.get("assignees") or []],
            "labels": [l.get("name", "") for l in row.get("labels") or []], "created_at": row.get("created_at"),
            "closed_at": row.get("closed_at"), "updated_at": row.get("updated_at"), "url": row.get("html_url"),
            "milestone_due": (row.get("milestone") or {}).get("due_on")}


def collect(client, start, end, deployed_commit=""):
    """Everything the agenda needs for [start, end) (aware datetimes), as plain JSON-able dicts."""
    warnings = []
    repo, _ = client.get("")
    default = repo.get("default_branch") or "main"
    within = lambda value: value is not None and start <= parse_time(value) < end

    pulls, truncated = client.pages("/pulls", {"state": "all", "sort": "updated", "direction": "desc"},
                                    stop=lambda row: parse_time(row.get("updated_at")) < start and row.get("state") != "open")
    if truncated: warnings.append("Muitos pull requests na semana; a lista foi limitada.")
    # Open PRs without activity this week still are pending work: listed separately, merged by number.
    open_rows, truncated = client.pages("/pulls", {"state": "open", "sort": "updated", "direction": "desc"})
    if truncated: warnings.append("Muitos pull requests abertos; a lista foi limitada.")
    known = {p["number"] for p in pulls}
    pulls = [_pr(p) for p in pulls + [o for o in open_rows if o["number"] not in known]]
    week_pulls = [p for p in pulls if p["state"] == "open" or any(within(p[k]) for k in ("created_at", "merged_at", "closed_at", "updated_at"))]

    in_pr = set()
    for pr in week_pulls[:MAX_DETAIL]:
        rows, _ = client.pages(f"/pulls/{pr['number']}/commits", {})
        pr["commits"] = [r.get("sha") for r in rows]
        in_pr.update(pr["commits"])
    if len(week_pulls) > MAX_DETAIL: warnings.append("Commits de alguns PRs não foram detalhados (limite de consultas).")

    branches, more = client.pages("/branches", {})
    if more or len(branches) > MAX_BRANCHES: warnings.append(f"Mais de {MAX_BRANCHES} branches; somente as primeiras foram consultadas.")
    commits = {}
    for branch in [b.get("name") for b in branches][:MAX_BRANCHES]:
        rows, _ = client.pages("/commits", {"sha": branch, "since": start.isoformat(), "until": end.isoformat()})
        for row in rows:
            if row.get("sha") in commits:
                commits[row["sha"]]["branches"].append(branch)
            else:
                commits[row["sha"]] = _commit(row, branch)

    issues, more = client.pages("/issues", {"state": "all", "since": start.isoformat(), "sort": "updated", "direction": "desc"})
    open_issues, more_open = client.pages("/issues", {"state": "open", "sort": "updated", "direction": "desc"})
    if more or more_open: warnings.append("Muitas issues; a lista foi limitada.")
    seen, all_issues = set(), []
    for row in issues + open_issues:
        if "pull_request" in row or row["number"] in seen:
            continue
        seen.add(row["number"])
        all_issues.append(_issue(row))

    for pr in week_pulls[:MAX_DETAIL]:
        if not pr["head_sha"] or not SHA.fullmatch(pr["head_sha"]):
            continue
        data, _ = client.get(f"/commits/{pr['head_sha']}/check-runs", {"per_page": 100})
        runs = [r for r in (data or {}).get("check_runs", []) if isinstance(r, dict)]
        conclusions = [r.get("conclusion") or r.get("status") for r in runs]
        pr["ci"] = {"total": len(runs), "failed": [r.get("name") for r in runs if r.get("conclusion") in {"failure", "timed_out", "cancelled", "action_required"}],
                    "pending": sum(1 for c in conclusions if c in {"queued", "in_progress", None}),
                    "passed": sum(1 for c in conclusions if c in {"success", "neutral", "skipped"}),
                    "url": pr["url"] + "/checks" if pr["url"] else None}

    deployed = {"commit": deployed_commit or "", "checked": False}
    if deployed_commit:
        if not SHA.fullmatch(deployed_commit):
            warnings.append("PRM_DEPLOYED_COMMIT inválido; implantação não verificada.")
        else:
            deployed["checked"] = True
            for pr in [p for p in pulls if p["merged_at"] and p["merge_commit_sha"]][:MAX_DETAIL]:
                if not SHA.fullmatch(pr["merge_commit_sha"]):
                    continue
                try:
                    data, _ = client.get(f"/compare/{pr['merge_commit_sha']}...{deployed_commit}")
                    pr["deployed"] = data.get("status") in {"ahead", "identical"}
                except GitHubError:
                    pr["deployed"] = None
    else:
        warnings.append("Commit implantado não informado (PRM_DEPLOYED_COMMIT): nada é considerado implantado.")

    return {"repository": client.repository, "default_branch": default, "private": bool(repo.get("private")),
            "pulls": [p for p in pulls if p in week_pulls or p.get("deployed") is not None],
            "commits": sorted(commits.values(), key=lambda c: c["date"] or "", reverse=True),
            "commits_in_pr": sorted(in_pr), "issues": all_issues, "deployment": deployed,
            "token_scopes": client.scopes, "calls": client.calls, "warnings": warnings,
            "collected_at": datetime.now(timezone.utc).isoformat()}


def is_bug(labels, title):
    return bool({l.lower() for l in labels} & BUG_LABELS) or bool(BUG_TITLE.search(title or ""))


def needs_decision(labels):
    return bool({l.lower() for l in labels} & DECISION_LABELS)
