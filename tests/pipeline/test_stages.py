"""Tests for mga.pipeline.stages — PipelineContext and PipelineStage ABC."""

from mga.models import Page, ProjectConfig, TranslationCandidate
from mga.pipeline.stages import PipelineContext, PipelineStage


def test_pipeline_context_defaults():
    ctx = PipelineContext()
    assert ctx.pages == []
    assert ctx.translations == []
    assert ctx.errors == []
    assert ctx.artifacts == {}


def test_pipeline_context_mutation():
    ctx = PipelineContext()
    ctx.pages.append(Page(page_id="p1"))
    ctx.translations.append(TranslationCandidate(bubble_id="b1", text="hello"))
    ctx.errors.append({"stage": "test", "error": "oops"})
    assert len(ctx.pages) == 1
    assert len(ctx.translations) == 1
    assert len(ctx.errors) == 1


def test_pipeline_stage_abc():
    # Verify ABC cannot be instantiated
    with pytest.raises(TypeError):
        PipelineStage()


def test_concrete_stage():
    class DummyStage(PipelineStage):
        @property
        def name(self): return "dummy"

        @property
        def order(self): return 99

        def execute(self, context):
            context.artifacts["dummy"] = {"ran": True}
            return context

    stage = DummyStage()
    assert stage.name == "dummy"
    assert stage.order == 99

    ctx = PipelineContext()
    result = stage.execute(ctx)
    assert result.artifacts["dummy"]["ran"] is True


import pytest
