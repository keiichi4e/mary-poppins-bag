#!/usr/bin/env python3
"""Move Linear issues or projects between teams with preview support."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

ENDPOINT = "https://api.linear.app/graphql"


class LinearError(RuntimeError):
    """Raised when the Linear API returns an error."""


def unwrap_type(type_info: dict[str, Any] | None) -> tuple[str | None, str | None]:
    """Return the outer kind and innermost named type."""
    outer_kind = None
    current = type_info
    while current:
        if outer_kind is None:
            outer_kind = current.get("kind")
        name = current.get("name")
        if name:
            return outer_kind, name
        current = current.get("ofType")
    return outer_kind, None


def auth_header() -> str:
    explicit = os.getenv("LINEAR_AUTH_HEADER")
    if explicit:
        return explicit
    api_key = os.getenv("LINEAR_API_KEY")
    if not api_key:
        raise LinearError("Set LINEAR_API_KEY or LINEAR_AUTH_HEADER before running this script.")
    if api_key.startswith("Bearer "):
        return api_key
    return api_key


def graphql(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    request = urllib.request.Request(
        ENDPOINT,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": auth_header(),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise LinearError(f"Linear API HTTP {exc.code}: {details}") from exc
    except urllib.error.URLError as exc:
        raise LinearError(f"Failed to reach Linear API: {exc}") from exc

    data = json.loads(body)
    errors = data.get("errors") or []
    if errors:
        messages = "; ".join(error.get("message", "Unknown GraphQL error") for error in errors)
        raise LinearError(messages)
    return data["data"]


def get_type_details(type_name: str) -> dict[str, Any]:
    data = graphql(
        """
        query TypeDetails($typeName: String!) {
          __type(name: $typeName) {
            name
            kind
            fields {
              name
              type {
                kind
                name
                ofType {
                  kind
                  name
                  ofType {
                    kind
                    name
                    ofType {
                      kind
                      name
                    }
                  }
                }
              }
            }
            inputFields {
              name
              type {
                kind
                name
                ofType {
                  kind
                  name
                  ofType {
                    kind
                    name
                    ofType {
                      kind
                      name
                    }
                  }
                }
              }
            }
          }
        }
        """,
        {"typeName": type_name},
    )
    type_info = data.get("__type")
    if not type_info:
        raise LinearError(f"GraphQL type {type_name!r} was not found.")
    return type_info


def supported_fields(type_name: str) -> set[str]:
    return {field["name"] for field in get_type_details(type_name).get("fields") or []}


def supported_input_fields(type_name: str) -> dict[str, tuple[str | None, str | None]]:
    result: dict[str, tuple[str | None, str | None]] = {}
    for field in get_type_details(type_name).get("inputFields") or []:
        result[field["name"]] = unwrap_type(field.get("type"))
    return result


def query_root_fields() -> set[str]:
    schema = graphql(
        """
        query QueryRoot {
          __schema {
            queryType {
              fields {
                name
              }
            }
          }
        }
        """
    )
    return {
        field["name"]
        for field in schema["__schema"]["queryType"]["fields"]
    }


def mutation_root_fields() -> set[str]:
    schema = graphql(
        """
        query MutationRoot {
          __schema {
            mutationType {
              fields {
                name
              }
            }
          }
        }
        """
    )
    mutation_type = schema["__schema"].get("mutationType")
    if not mutation_type:
        return set()
    return {field["name"] for field in mutation_type["fields"]}


@dataclass
class TeamRecord:
    id: str
    name: str
    key: str | None = None

    def display(self) -> str:
        if self.key:
            return f"{self.name} ({self.key}, {self.id})"
        return f"{self.name} ({self.id})"


def fetch_teams() -> list[TeamRecord]:
    fields = supported_fields("Team")
    selection = ["id", "name"]
    if "key" in fields:
        selection.append("key")
    data = graphql(
        f"""
        query Teams {{
          teams {{
            nodes {{
              {" ".join(selection)}
            }}
          }}
        }}
        """
    )
    teams = []
    for node in data["teams"]["nodes"]:
        teams.append(TeamRecord(id=node["id"], name=node["name"], key=node.get("key")))
    return teams


def resolve_team(ref: str) -> TeamRecord:
    teams = fetch_teams()
    lowered = ref.casefold()
    matches = [
        team
        for team in teams
        if team.id == ref
        or team.name.casefold() == lowered
        or (team.key and team.key.casefold() == lowered)
    ]
    if not matches:
        raise LinearError(f"No team matched {ref!r}. Run list-teams and retry with an exact name or UUID.")
    if len(matches) > 1:
        labels = ", ".join(team.display() for team in matches)
        raise LinearError(f"Team reference {ref!r} is ambiguous: {labels}")
    return matches[0]


def issue_selection() -> str:
    fields = supported_fields("Issue")
    team_fields = supported_fields("Team")
    desired = ["id", "title", "identifier", "url"]
    selection = [field for field in desired if field in fields]
    if "team" in fields:
        desired_team = [field for field in ["id", "name", "key"] if field in team_fields]
        selection.append(f"team {{ {' '.join(desired_team)} }}")
    return " ".join(selection)


def fetch_issue(issue_ref: str) -> dict[str, Any]:
    if "issue" not in query_root_fields():
        raise LinearError("This workspace schema does not expose the issue query.")
    data = graphql(
        f"""
        query Issue($id: String!) {{
          issue(id: $id) {{
            {issue_selection()}
          }}
        }}
        """,
        {"id": issue_ref},
    )
    issue = data.get("issue")
    if not issue:
        raise LinearError(f"Issue {issue_ref!r} was not found.")
    return issue


def project_selection() -> str:
    fields = supported_fields("Project")
    team_fields = supported_fields("Team")
    desired_project = [field for field in ["id", "name", "slugId", "url"] if field in fields]
    desired_team = [field for field in ["id", "name", "key"] if field in team_fields]
    if "teams" in fields:
        desired_project.append(f"teams {{ nodes {{ {' '.join(desired_team)} }} }}")
    return " ".join(desired_project)


def fetch_project(project_id: str) -> dict[str, Any]:
    roots = query_root_fields()
    if "project" not in roots:
        raise LinearError("This workspace schema does not expose the project query.")
    data = graphql(
        f"""
        query Project($id: String!) {{
          project(id: $id) {{
            {project_selection()}
          }}
        }}
        """,
        {"id": project_id},
    )
    project = data.get("project")
    if not project:
        raise LinearError(f"Project {project_id!r} was not found.")
    return project


def require_mutation(name: str) -> None:
    if name not in mutation_root_fields():
        raise LinearError(f"This workspace schema does not expose the {name} mutation.")


def move_issue(issue_ref: str, target_team_ref: str, dry_run: bool) -> int:
    require_mutation("issueUpdate")
    inputs = supported_input_fields("IssueUpdateInput")
    if "teamId" not in inputs:
        present = ", ".join(sorted(inputs))
        raise LinearError(f"IssueUpdateInput lacks teamId. Available fields: {present}")

    issue = fetch_issue(issue_ref)
    target_team = resolve_team(target_team_ref)
    current_team = issue.get("team") or {}
    current_label = current_team.get("name", "<unknown>")

    print(f"Issue: {issue.get('identifier', issue.get('id'))} {issue.get('title', '')}".strip())
    print(f"Current team: {current_label}")
    print(f"Target team: {target_team.display()}")

    if dry_run:
        print("Dry run only. No mutation sent.")
        return 0

    data = graphql(
        f"""
        mutation MoveIssue($id: String!, $input: IssueUpdateInput!) {{
          issueUpdate(id: $id, input: $input) {{
            success
            issue {{
              {issue_selection()}
            }}
          }}
        }}
        """,
        {"id": issue_ref, "input": {"teamId": target_team.id}},
    )
    payload = data["issueUpdate"]
    if not payload.get("success"):
        raise LinearError("issueUpdate returned success=false.")
    updated = payload["issue"]
    updated_team = (updated.get("team") or {}).get("name", "<unknown>")
    print(f"Updated team: {updated_team}")
    return 0


def compute_project_team_ids(
    project: dict[str, Any],
    source_team: TeamRecord | None,
    target_team: TeamRecord,
) -> list[str]:
    current = [node["id"] for node in project.get("teams", {}).get("nodes", [])]
    result = [team_id for team_id in current if not source_team or team_id != source_team.id]
    if target_team.id not in result:
        result.append(target_team.id)
    return result


def move_project(
    project_id: str,
    target_team_ref: str,
    source_team_ref: str | None,
    dry_run: bool,
) -> int:
    require_mutation("projectUpdate")
    inputs = supported_input_fields("ProjectUpdateInput")
    if "teamIds" not in inputs:
        present = ", ".join(sorted(inputs))
        raise LinearError(
            "ProjectUpdateInput lacks teamIds. "
            f"Available fields: {present}"
        )
    outer_kind, inner_name = inputs["teamIds"]
    if outer_kind != "LIST":
        raise LinearError(f"ProjectUpdateInput.teamIds is not a list field (found {outer_kind}/{inner_name}).")

    project = fetch_project(project_id)
    target_team = resolve_team(target_team_ref)
    source_team = resolve_team(source_team_ref) if source_team_ref else None

    current_nodes = project.get("teams", {}).get("nodes", [])
    current_ids = [node["id"] for node in current_nodes]
    if source_team and source_team.id not in current_ids:
        raise LinearError(
            f"Project is not currently attached to source team {source_team.display()}."
        )

    next_team_ids = compute_project_team_ids(project, source_team, target_team)
    team_lookup = {team.id: team for team in fetch_teams()}

    print(f"Project: {project.get('name', project.get('id'))} ({project.get('id')})")
    print("Current teams:")
    for node in current_nodes:
        team = team_lookup.get(node["id"])
        print(f"- {(team.display() if team else node['id'])}")
    print("Planned teams:")
    for team_id in next_team_ids:
        team = team_lookup.get(team_id)
        print(f"- {(team.display() if team else team_id)}")

    if dry_run:
        print("Dry run only. No mutation sent.")
        return 0

    data = graphql(
        f"""
        mutation MoveProject($id: String!, $input: ProjectUpdateInput!) {{
          projectUpdate(id: $id, input: $input) {{
            success
            project {{
              {project_selection()}
            }}
          }}
        }}
        """,
        {"id": project_id, "input": {"teamIds": next_team_ids}},
    )
    payload = data["projectUpdate"]
    if not payload.get("success"):
        raise LinearError("projectUpdate returned success=false.")
    updated_teams = payload["project"].get("teams", {}).get("nodes", [])
    print("Updated teams:")
    for node in updated_teams:
        team = team_lookup.get(node["id"])
        print(f"- {(team.display() if team else node['id'])}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list-teams", help="List visible teams.")

    issue_parser = subparsers.add_parser("move-issue", help="Move one issue to another team.")
    issue_parser.add_argument("--issue", required=True, help="Issue UUID or identifier such as ENG-123.")
    issue_parser.add_argument("--target-team", required=True, help="Target team UUID, key, or exact name.")
    issue_parser.add_argument("--dry-run", action="store_true", help="Preview without mutating.")

    project_parser = subparsers.add_parser("move-project", help="Move one project between teams.")
    project_parser.add_argument("--project", required=True, help="Project UUID.")
    project_parser.add_argument("--target-team", required=True, help="Target team UUID, key, or exact name.")
    project_parser.add_argument("--source-team", help="Source team UUID, key, or exact name to remove.")
    project_parser.add_argument("--dry-run", action="store_true", help="Preview without mutating.")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "list-teams":
        for team in fetch_teams():
            print(team.display())
        return 0
    if args.command == "move-issue":
        return move_issue(args.issue, args.target_team, args.dry_run)
    if args.command == "move-project":
        return move_project(args.project, args.target_team, args.source_team, args.dry_run)
    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except LinearError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
