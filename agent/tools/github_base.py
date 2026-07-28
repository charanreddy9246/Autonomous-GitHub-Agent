from agent.github_client import GitHubClient

TOOL_SPECS = {
    "list_issues": {
        "description": "List issues in the repo, optionally filtered by state, labels, or assignee.",
        "parameters": {
            "type": "object",
            "properties": {
                "state": {"type": "string", "enum": ["open", "closed", "all"], "default": "open"},
                "labels": {"type": "string", "description": "comma-separated label names"},
                "assignee": {"type": "string", "description": "'none' for unassigned"},
            },
        },
    },
    "create_issue": {
        "description": "Create a new issue.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "body": {"type": "string"},
                "labels": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["title"],
        },
    },
    "add_comment": {
        "description": "Add a comment to an existing issue.",
        "parameters": {
            "type": "object",
            "properties": {
                "issue_number": {"type": "integer"},
                "body": {"type": "string"},
            },
            "required": ["issue_number", "body"],
        },
    },
    "get_issue": {
        "description": "Fetch a single issue by number.",
        "parameters": {
            "type": "object",
            "properties": {"issue_number": {"type": "integer"}},
            "required": ["issue_number"],
        },
    },
}


def list_issues(args: dict, client: GitHubClient):
    params = {"state": args.get("state", "open"), "per_page": 100}
    if args.get("labels"):
        params["labels"] = args["labels"]
    if args.get("assignee"):
        params["assignee"] = args["assignee"]
    issues = client.get(client.repo_path("/issues"), params=params)
    return [
        {
            "number": i["number"],
            "title": i["title"],
            "state": i["state"],
            "labels": [l["name"] for l in i.get("labels", [])],
            "assignee": i["assignee"]["login"] if i.get("assignee") else None,
            "body": i.get("body") or "",
        }
        for i in issues
        if "pull_request" not in i
    ]


def create_issue(args: dict, client: GitHubClient):
    payload = {"title": args["title"]}
    if args.get("body"):
        payload["body"] = args["body"]
    if args.get("labels"):
        payload["labels"] = args["labels"]
    result = client.post(client.repo_path("/issues"), json=payload)
    return {"number": result["number"], "url": result["html_url"]}


def add_comment(args: dict, client: GitHubClient):
    result = client.post(
        client.repo_path(f"/issues/{args['issue_number']}/comments"),
        json={"body": args["body"]},
    )
    return {"id": result["id"], "url": result["html_url"]}


def get_issue(args: dict, client: GitHubClient):
    i = client.get(client.repo_path(f"/issues/{args['issue_number']}"))
    return {
        "number": i["number"],
        "title": i["title"],
        "state": i["state"],
        "labels": [l["name"] for l in i.get("labels", [])],
        "body": i.get("body") or "",
    }


BASE_TOOLS = {
    "list_issues": list_issues,
    "create_issue": create_issue,
    "add_comment": add_comment,
    "get_issue": get_issue,
}
