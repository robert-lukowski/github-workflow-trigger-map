# github-workflow-trigger-map

`github-workflow-trigger-map` is a small CLI tool that scans a repository's
GitHub Actions workflow files, detects their triggers and relationships, and
prints a readable trigger map plus a Mermaid flowchart.

The [`examples/sample-repo`](examples/sample-repo) directory contains harmless,
synthetic workflows used as a test fixture. They are nested below the example
repository so they do not run as GitHub Actions for this repository.

## Installation

```
python -m pip install -r requirements.txt
```

## Usage

```
python workflow_map.py examples/sample-repo
```

The tool prints a terminal summary of each workflow's triggers and
relationships, and generates `workflow-map.md` containing a Mermaid diagram
of the same information.

## Supported trigger types

- `push`
- `pull_request`
- `workflow_dispatch`
- `schedule`
- `workflow_run`
- `workflow_call`

## Current limitations

This is a lightweight MVP. It does not attempt to model every GitHub Actions
edge case (e.g. all possible trigger filter combinations, workflows split
across multiple `on:` config styles, or reusable workflows hosted in other
repositories). `workflow_run` relationships are matched by workflow name,
and reusable workflow calls are only detected when they point at a local
`.github/workflows/...` file.
