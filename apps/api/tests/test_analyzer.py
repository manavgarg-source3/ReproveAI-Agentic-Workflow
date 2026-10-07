"""Tests for the provider-neutral analyzer boundary."""

from app.schemas.research import Experiment, PaperMetadata, ResearchAnalysis
from app.services.analyzer import (
    _enrich_explicit_global_protocols,
    analyze_research_text,
    merge_research_analyses,
)


class StubProvider:
    closed = False

    def analyze(self, text: str) -> ResearchAnalysis:
        assert "paper" in text
        return ResearchAnalysis(paper=PaperMetadata(title="Stub Paper"))

    def close(self) -> None:
        self.closed = True


def test_analyzer_uses_injected_provider() -> None:
    result = analyze_research_text("paper", provider=StubProvider())

    assert result.paper.title == "Stub Paper"


def test_merge_combines_partial_duplicate_experiment_and_preserves_result() -> None:
    first = ResearchAnalysis(
        paper=PaperMetadata(title="Dataset Condensation"),
        experiments=[Experiment(
            id="EXP-A",
            objective=(
                "Compare classification performance with condensed images against "
                "coreset methods on MNIST with 50 images per class using ConvNet"
            ),
            dataset="MNIST",
            split="test",
            model="ConvNet",
            metric="testing accuracy",
            evidence_locations=["Table 1"],
        )],
    )
    second = ResearchAnalysis(
        paper=PaperMetadata(title="Dataset Condensation"),
        experiments=[Experiment(
            id="EXP-B",
            objective=(
                "Compare classification performance with condensed images against "
                "coreset methods on MNIST with 50 images per class using ConvNet for our method"
            ),
            dataset="MNIST",
            split="test",
            model="ConvNet",
            metric="testing accuracy",
            reported_result=98.8,
            evidence_locations=["Section 3.1"],
        )],
    )

    merged = merge_research_analyses([first, second])

    assert len(merged.experiments) == 1
    assert merged.experiments[0].reported_result == 98.8
    assert merged.experiments[0].evidence_locations == ["Table 1", "Section 3.1"]


def test_merge_treats_baseline_wording_as_metadata_not_experiment_identity() -> None:
    shared = dict(
        dataset="MNIST", split="test", model="ConvNet",
        metric="testing accuracy", reported_result=98.8,
    )
    first = ResearchAnalysis(
        paper=PaperMetadata(title="Dataset Condensation"),
        experiments=[Experiment(
            id="EXP-A", objective="Evaluate MNIST with 50 images per class",
            baseline="coreset methods", **shared,
        )],
    )
    second = ResearchAnalysis(
        paper=PaperMetadata(title="Dataset Condensation"),
        experiments=[Experiment(
            id="EXP-B", objective="Evaluate our method on MNIST with 50 images per class",
            baseline="random selection", **shared,
        )],
    )

    merged = merge_research_analyses([first, second])

    assert len(merged.experiments) == 1


def test_explicit_global_train_test_protocol_enriches_testing_result_split() -> None:
    analysis = ResearchAnalysis(
        paper=PaperMetadata(title="Dataset Condensation"),
        experiments=[Experiment(
            id="EXP-TEST",
            objective="Compare testing accuracy on CIFAR10",
            dataset="CIFAR10",
            model="ConvNet",
            metric="testing accuracy",
            reported_result=49.9,
        )],
    )

    enriched = _enrich_explicit_global_protocols(
        analysis,
        "In all experiments, we use the standard train/test splits of the datasets.",
    )

    assert enriched.experiments[0].split == "test"
