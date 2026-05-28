"""Tests for the governed swarm (orchestrator). Fully offline: EchoProvider +
explicit sub-tasks, so no network and no model are needed."""

from __future__ import annotations

import pytest

from agent_os.orchestrator import Orchestrator, SubTask, _split_enumerated
from agent_os.providers import EchoProvider
from agent_os.skill_registry import SkillRegistry


@pytest.fixture
def orch(tmp_path):
    return Orchestrator(
        provider=EchoProvider(),
        skills=SkillRegistry(tmp_path / "noskills"),  # empty → no skill injection
        state_dir=str(tmp_path / "state"),
        traces_dir=str(tmp_path / "traces"),
        jobs_db=str(tmp_path / "state" / "jobs.db"),
        concurrency=3,
    )


def test_runs_explicit_subtasks_in_parallel(orch) -> None:
    res = orch.run("research goal", subtasks=["analyze alpha", "analyze beta", "analyze gamma"])
    assert len(res.results) == 3
    assert len(res.done) == 3 and not res.gated and not res.failed
    # each sub-task became a real, scored job
    for r in res.done:
        assert r.job_id and r.output.startswith("[echo]")
    # synthesis produced a deliverable and was itself scored as a job
    assert res.deliverable
    assert res.synthesis_job_id is not None


def test_default_deny_gates_privileged_subtasks(orch) -> None:
    res = orch.run("mixed goal", subtasks=[
        "summarize the latest research",        # read-only → runs
        "delete the production database",        # privileged → gated
        "deploy to production",                  # privileged → gated
    ])
    gated_tasks = {r.task for r in res.gated}
    assert "delete the production database" in gated_tasks
    assert "deploy to production" in gated_tasks
    assert len(res.done) == 1                    # only the read-only one ran


def test_render_reports_counts(orch) -> None:
    out = orch.run("g", subtasks=["a", "b"]).render()
    assert "Swarm: g" in out and "2 sub-task" in out
    assert "--- Deliverable ---" in out


def test_decompose_enumerated_offline(tmp_path) -> None:
    # No provider → split a goal that already enumerates its items.
    o = Orchestrator(state_dir=str(tmp_path), traces_dir=str(tmp_path / "t"))
    subs = o.decompose("- review the intro\n- review the methods\n- review the results")
    assert [s.task for s in subs] == ["review the intro", "review the methods", "review the results"]


def test_decompose_single_goal_is_one_subtask(tmp_path) -> None:
    o = Orchestrator(state_dir=str(tmp_path), traces_dir=str(tmp_path / "t"))
    subs = o.decompose("write a short poem about the sea")
    assert len(subs) == 1


def test_decompose_via_model_json(tmp_path) -> None:
    class JsonProvider(EchoProvider):
        def complete(self, prompt, *, system=None):
            return '```json\n[{"title":"A","task":"do a"},{"title":"B","task":"do b"}]\n```'

    o = Orchestrator(provider=JsonProvider(), state_dir=str(tmp_path),
                     traces_dir=str(tmp_path / "t"))
    subs = o.decompose("anything")
    assert [s.task for s in subs] == ["do a", "do b"]


def test_split_enumerated_helper() -> None:
    assert _split_enumerated("a; b; c") == ["a", "b", "c"]
    assert _split_enumerated("1. first\n2. second") == ["first", "second"]


def test_max_subtasks_cap(tmp_path) -> None:
    o = Orchestrator(state_dir=str(tmp_path), traces_dir=str(tmp_path / "t"),
                     max_subtasks=2)
    res = o.run("g", subtasks=[SubTask("x", "x"), SubTask("y", "y"), SubTask("z", "z")])
    assert len(res.results) == 2
