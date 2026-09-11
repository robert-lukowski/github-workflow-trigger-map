#!/usr/bin/env python3
"""Analyze GitHub Actions workflow files and print/generate a trigger map.

Usage:
    python workflow_map.py <path-to-repo>

Scans <repo>/.github/workflows/*.yml(.yaml) for trigger definitions
(push, pull_request, workflow_dispatch, schedule, workflow_run,
workflow_call), detects relationships between workflows (workflow_run
"listens to" links and reusable workflow "calls" links), prints a
readable summary to the terminal, and writes a Mermaid flowchart to
workflow-map.md in the current directory.
"""

import sys
from pathlib import Path

import yaml


def load_workflows(repo_dir: Path):
    """Parse every workflow YAML file under .github/workflows/."""
    workflows_dir = repo_dir / ".github" / "workflows"
    workflows = []

    for path in sorted(workflows_dir.glob("*.yml")) + sorted(workflows_dir.glob("*.yaml")):
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        name = data.get("name") or path.stem
        # YAML parses the bare key "on" as boolean True, so check both.
        triggers = data.get("on", data.get(True, {})) or {}
        if isinstance(triggers, str):
            triggers = {triggers: None}
        elif isinstance(triggers, list):
            triggers = {t: None for t in triggers}

        called_workflows = find_reusable_calls(data)

        workflows.append(
            {
                "path": path,
                "file": path.name,
                "name": name,
                "triggers": triggers,
                "calls": called_workflows,
            }
        )

    return workflows


def find_reusable_calls(data):
    """Find local reusable workflow files referenced via `jobs.<id>.uses`."""
    calls = []
    jobs = data.get("jobs", {}) or {}
    for job in jobs.values():
        uses = job.get("uses") if isinstance(job, dict) else None
        if uses and ".github/workflows/" in uses:
            calls.append(uses.split("/")[-1].split("@")[0])
    return calls


def describe_push_or_pr(trigger_body):
    """Return a human readable branch filter description, if any."""
    if not isinstance(trigger_body, dict):
        return ""
    branches = trigger_body.get("branches")
    if branches:
        return f" (branches: {', '.join(branches)})"
    return ""


def build_trigger_lines(wf):
    """Return readable lines describing a workflow's triggers."""
    lines = []
    triggers = wf["triggers"]

    for key in ("push", "pull_request"):
        if key in triggers:
            lines.append(f"  - {key}{describe_push_or_pr(triggers[key])}")

    if "workflow_dispatch" in triggers:
        lines.append("  - workflow_dispatch")

    if "schedule" in triggers:
        crons = triggers["schedule"] or []
        cron_list = ", ".join(entry.get("cron", "?") for entry in crons if isinstance(entry, dict))
        lines.append(f"  - schedule ({cron_list})" if cron_list else "  - schedule")

    if "workflow_run" in triggers:
        body = triggers["workflow_run"] or {}
        upstream = body.get("workflows", []) if isinstance(body, dict) else []
        lines.append(f"  - workflow_run (watches: {', '.join(upstream)})")

    if "workflow_call" in triggers:
        lines.append("  - workflow_call (reusable workflow)")

    return lines


def resolve_workflow_run_links(workflows):
    """Match workflow_run 'workflows: [Name]' entries to actual workflow files.

    Matching is done by workflow display name, since that is what
    GitHub Actions itself uses. Returns a list of (watcher_file, source_file)
    tuples plus a list of names that couldn't be resolved.
    """
    by_name = {wf["name"]: wf for wf in workflows}
    links = []
    unresolved = []

    for wf in workflows:
        body = wf["triggers"].get("workflow_run")
        if not isinstance(body, dict):
            continue
        for source_name in body.get("workflows", []):
            source = by_name.get(source_name)
            if source:
                links.append((wf["file"], source["file"]))
            else:
                unresolved.append((wf["file"], source_name))

    return links, unresolved


def print_terminal_map(workflows, run_links, run_unresolved):
    print("=" * 60)
    print("GitHub Actions Workflow Trigger Map")
    print("=" * 60)

    for wf in workflows:
        print(f"\n{wf['name']}  ({wf['file']})")
        lines = build_trigger_lines(wf)
        if not lines:
            print("  - (no triggers detected)")
        else:
            print("\n".join(lines))
        if wf["calls"]:
            print(f"  -> calls reusable workflow(s): {', '.join(wf['calls'])}")

    print("\n" + "-" * 60)
    print("Relationships")
    print("-" * 60)

    if run_links:
        for watcher, source in run_links:
            print(f"  {watcher} --(workflow_run)--> triggered after {source}")
    for watcher, missing_name in run_unresolved:
        print(f"  {watcher} --(workflow_run)--> UNRESOLVED workflow named '{missing_name}'")

    calls_found = any(wf["calls"] for wf in workflows)
    if calls_found:
        for wf in workflows:
            for called in wf["calls"]:
                print(f"  {wf['file']} --(uses)--> {called}")

    if not run_links and not run_unresolved and not calls_found:
        print("  (none detected)")


def mermaid_node_id(filename):
    return filename.replace(".", "_").replace("-", "_")


SIMPLE_TRIGGER_LABELS = {
    "workflow_dispatch": "manual dispatch",
    "schedule": "schedule",
    "workflow_call": "workflow_call",
}


def build_mermaid(workflows, run_links):
    """Build a Mermaid flowchart: one node per workflow, one node per
    trigger, plus edges for workflow_run and reusable workflow calls."""
    lines = ["```mermaid", "flowchart TD"]

    for wf in workflows:
        node = mermaid_node_id(wf["file"])
        lines.append(f'    {node}["{wf["name"]}<br/>{wf["file"]}"]')

    for wf in workflows:
        node = mermaid_node_id(wf["file"])
        triggers = wf["triggers"]

        for key in ("push", "pull_request"):
            if key in triggers:
                suffix = describe_push_or_pr(triggers[key]).strip()
                text = f"{key}{(' ' + suffix) if suffix else ''}"
                lines.append(f'    {node}_{key}(("{text}")) --> {node}')

        for key, text in SIMPLE_TRIGGER_LABELS.items():
            if key in triggers:
                lines.append(f'    {node}_{key}(("{text}")) --> {node}')
        # workflow_run edges are drawn separately below via run_links

    for watcher, source in run_links:
        source_node = mermaid_node_id(source)
        watcher_node = mermaid_node_id(watcher)
        lines.append(f"    {source_node} -. workflow_run .-> {watcher_node}")

    for wf in workflows:
        node = mermaid_node_id(wf["file"])
        for called in wf["calls"]:
            lines.append(f"    {node} -- uses --> {mermaid_node_id(called)}")

    lines.append("```")
    return "\n".join(lines)


def main():
    if len(sys.argv) != 2:
        print("Usage: python workflow_map.py <path-to-repo>")
        sys.exit(1)

    repo_dir = Path(sys.argv[1]).resolve()
    workflows_dir = repo_dir / ".github" / "workflows"
    if not workflows_dir.is_dir():
        print(f"No .github/workflows directory found under {repo_dir}")
        sys.exit(1)

    workflows = load_workflows(repo_dir)
    if not workflows:
        print(f"No workflow files found under {workflows_dir}")
        sys.exit(1)

    run_links, run_unresolved = resolve_workflow_run_links(workflows)

    print_terminal_map(workflows, run_links, run_unresolved)

    mermaid = build_mermaid(workflows, run_links)
    out_path = Path("workflow-map.md")
    out_path.write_text(
        "# Workflow Trigger Map\n\n" + mermaid + "\n", encoding="utf-8"
    )
    print(f"\nMermaid diagram written to {out_path.resolve()}")

    if run_unresolved:
        print(
            "\nNote: some workflow_run references could not be resolved "
            "to a known workflow file (name mismatch or external workflow)."
        )


if __name__ == "__main__":
    main()
