"""Tests for composable before/after hooks and the built-in redaction hook."""

from __future__ import annotations

from agent_os.hooks import (
    HookContext,
    HookPhase,
    HookRegistry,
    redact_secrets,
    redaction_hook,
)


def _ctx(phase=HookPhase.AFTER, context="", output=None):
    return HookContext(phase=phase, command="task", profile="researcher",
                       job_id="job1", context=context, output=output)


def test_redact_secrets_masks_known_shapes():
    text = (
        "key sk-abcdefghijklmnopqrstuvwx token ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345 "
        "email alice@example.com bearer abcdef123456ZZZ"
    )
    out, found = redact_secrets(text)
    assert "sk-abcdefghijklmnopqrstuvwx" not in out
    assert "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345" not in out
    assert "alice@example.com" not in out
    assert "[REDACTED:openai-key]" in out
    assert {"openai-key", "github-token", "email"} <= set(found)


def test_redact_secrets_leaves_clean_text_untouched():
    out, found = redact_secrets("nothing secret here, just words")
    assert out == "nothing secret here, just words"
    assert found == []


def test_redaction_hook_redacts_output_after_phase():
    hook = redaction_hook()
    ctx = _ctx(phase=HookPhase.AFTER, output="here is sk-abcdefghijklmnopqrstuvwx")
    hook(ctx)
    assert "sk-abcdefghijklmnopqrstuvwx" not in ctx.output
    assert ctx.meta["redacted"]["output"] == ["openai-key"]


def test_redaction_hook_redacts_context_before_phase():
    hook = redaction_hook()
    ctx = _ctx(phase=HookPhase.BEFORE, context="leaked alice@example.com in memory")
    hook(ctx)
    assert "alice@example.com" not in ctx.context
    assert "email" in ctx.meta["redacted"]["context"]


def test_registry_runs_hooks_in_order():
    calls: list[str] = []
    reg = HookRegistry()
    reg.add_before(lambda c: calls.append("a"), name="a")
    reg.add_before(lambda c: calls.append("b"), name="b")
    reg.run_before(_ctx(phase=HookPhase.BEFORE))
    assert calls == ["a", "b"]


def test_registry_isolates_failing_hook():
    def boom(ctx):
        raise ValueError("nope")

    reg = HookRegistry()
    reg.add_after(boom, name="boom")
    reg.add_after(lambda c: c.meta.setdefault("ran", True), name="ok")
    ctx = reg.run_after(_ctx())
    assert ctx.meta.get("ran") is True
    assert any("boom" in e for e in ctx.meta["hook_errors"])


def test_default_registry_includes_redaction():
    reg = HookRegistry.default()
    assert "redaction" in reg.names["before"]
    assert "redaction" in reg.names["after"]
    ctx = reg.run_after(_ctx(output="sk-abcdefghijklmnopqrstuvwx"))
    assert "[REDACTED:openai-key]" in ctx.output


def test_add_registers_both_phases():
    reg = HookRegistry()
    reg.add(lambda c: None, name="dual")
    assert reg.names["before"] == ["dual"]
    assert reg.names["after"] == ["dual"]
