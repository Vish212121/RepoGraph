from app.agent.router import route_question


def test_router_selects_multi_hop_file_history() -> None:
    route = route_question("Show the history of src/flask/app.py")
    assert route.intent == "file_history"
    assert route.arguments == {"path_fragment": "src/flask/app.py"}


def test_router_selects_line_level_change_detail() -> None:
    route = route_question("What exactly changed in src/flask/app.py?")
    assert route.intent == "file_change_detail"
    assert route.arguments == {"path_fragment": "src/flask/app.py"}


def test_router_selects_commit_impact() -> None:
    route = route_question("What files were affected by commit d086db856be1872?")
    assert route.intent == "commit_impact"
    assert route.arguments["commit_prefix"] == "d086db856be1872"


def test_router_selects_dependency_impact_analysis() -> None:
    route = route_question("What files may be affected if src/flask/app.py changes?")
    assert route.intent == "impact_analysis"
    assert route.arguments == {"file_path": "src/flask/app.py"}


def test_router_selects_reviewer_recommendation() -> None:
    route = route_question("Who should review changes to src/flask/app.py?")
    assert route.intent == "suggest_reviewers"
    assert route.arguments == {"file_paths": ["src/flask/app.py"]}


def test_router_selects_decision_tracing() -> None:
    route = route_question("Why was the current request-handling design chosen, and was an earlier decision replaced?")
    assert route.intent == "trace_decision"
    assert route.arguments["topic"] == "Why was the current request-handling design chosen, and was an earlier decision replaced?"


def test_router_refuses_unsupported_questions() -> None:
    assert route_question("Explain the runtime behavior of this code").intent == "unsupported"
