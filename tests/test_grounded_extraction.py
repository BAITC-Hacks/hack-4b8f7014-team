from app.extraction import Candidate, grounded_task


def candidate(**changes):
    fields = dict(
        assignment_type="new_assignment",
        description="Подготовить отчёт",
        source_segments=[0],
        evidence="Подготовить отчёт",
        responsible="Анна",
        responsible_evidence="Анна, подготовить отчёт до пятницы",
        deadline_text="до пятницы",
        deadline_evidence="Анна, подготовить отчёт до пятницы",
        deadline=None,
    )
    fields.update(changes)
    return Candidate(**fields)


def test_unsupported_owner_and_historical_deadline_are_cleared():
    items = {0: {"text": "Подготовить отчёт до пятницы", "speaker_id": "S0"}}
    task = grounded_task(
        candidate(responsible="Председатель", deadline_text="в марте", deadline_evidence="в марте"),
        items,
        None,
    )
    assert task.responsible is None
    assert task.deadline_text is None
    assert len(task.review_warnings) == 2
    assert task.speaker_id == "S0"


def test_adjacent_segments_support_quote_without_assuming_source_is_assignee():
    items = {
        0: {"text": "Анна, Подготовить отчёт", "speaker_id": "CHAIR"},
        1: {"text": "до пятницы", "speaker_id": "CHAIR"},
    }
    c = candidate(
        source_segments=[0, 1],
        responsible_evidence="Анна, Подготовить отчёт",
        deadline_evidence="до пятницы",
    )
    task = grounded_task(c, items, None)
    assert task.responsible == "Анна"
    assert task.speaker_id == "CHAIR"
    assert task.deadline_text == "до пятницы"


def test_no_year_is_invented_without_meeting_date():
    from datetime import date

    items = {0: {"text": "Анна, Подготовить отчёт до 15 октября", "speaker_id": "S0"}}
    task = grounded_task(
        candidate(
            responsible_evidence=items[0]["text"],
            deadline_text="до 15 октября",
            deadline_evidence="до 15 октября",
            deadline=date(2026, 10, 15),
        ),
        items,
        None,
    )
    assert task.deadline is None
    assert task.deadline_text == "до 15 октября"


def test_unique_literal_quote_repairs_wrong_segment_id():
    items = {
        0: {"text": "Анна, Подготовить отчёт до пятницы", "speaker_id": "S0"},
        1: {"text": "Другая тема", "speaker_id": "S1"},
    }
    task = grounded_task(
        candidate(
            source_segments=[1],
            responsible_evidence=items[0]["text"],
            deadline_evidence="до пятницы",
        ),
        items,
        None,
    )
    assert task.evidence_status == "verified"
    assert task.speaker_id == "S0"
    assert task.responsible == "Анна"


def test_short_timing_gap_only_bridges_agreeing_speakers():
    from app.adapters import align_speakers
    from app.schemas import Segment

    words = [
        Segment(start=0, end=0.3, text="Первое"),
        Segment(start=0.3, end=1, text="сделайте"),
        Segment(start=1, end=1.3, text="отчёт"),
    ]
    turns = [(0, 0.3, "A"), (0.8, 1.3, "A")]
    result = align_speakers(words, turns, bridge_gaps=True)
    assert len(result) == 1 and result[0].speaker_id == "A"
    turns = [(0, 0.3, "A"), (0.8, 1.3, "B")]
    result = align_speakers(words, turns, bridge_gaps=True)
    assert result[1].speaker_id is None


def test_zero_duration_word_with_overlapping_voices_is_unknown():
    from app.adapters import align_speakers
    from app.schemas import Segment

    result = align_speakers([Segment(start=0.5, end=0.5, text="да")], [(0, 1, "A"), (0, 1, "B")])
    assert result[0].speaker_id is None


def test_pipeline_filters_past_events_and_preserves_numeric_facts(monkeypatch):
    import json

    import httpx

    from app.config import Settings
    from app.extraction import GroundedExtractor
    from app.schemas import ProcessOptions, Segment

    text = "Подготовить отчёт до пятницы. Потери 8%."
    item = candidate(
        responsible=None, responsible_evidence=None, deadline_evidence="до пятницы"
    ).model_dump(mode="json")
    past = {**item, "assignment_type": "past_event", "description": "Был инструктаж"}
    draft = {
        "tasks": [item, past],
        "facts": [
            {
                "direction": "Логистика",
                "indicator": "Потери 8%",
                "problem": "Потери",
                "evidence": "Потери 8%.",
                "source_segments": [0],
            }
        ],
    }
    replies = iter(
        [
            {"candidates": [{"source_segment": 0, "quote": "Подготовить отчёт"}]},
            draft,
            {"facts": draft["facts"]},
            {"tasks": draft["tasks"]},
            {"text": "Обсудили логистику."},
        ]
    )
    real_client = httpx.Client

    def handler(request):
        return httpx.Response(200, json={"message": {"content": json.dumps(next(replies))}})

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: real_client(**kwargs, transport=httpx.MockTransport(handler)),
    )
    extractor = GroundedExtractor(Settings(_env_file=None, stt_device="cpu"))
    summary, tasks = extractor.extract([Segment(start=0, end=5, text=text)], ProcessOptions())
    assert len(tasks) == 1
    assert "8%" in summary
    assert tasks[0].deadline_text == "до пятницы"


def test_permission_to_speak_does_not_assign_the_chair():
    items = {0: {"text": "Иван, можно добавить? Подготовить отчёт до пятницы", "speaker_id": "S0"}}
    task = grounded_task(
        candidate(
            responsible="Иван",
            responsible_evidence=items[0]["text"],
            deadline_evidence="до пятницы",
        ),
        items,
        None,
    )
    assert task.responsible is None
    assert task.review_warnings


def test_literal_numeric_facts_survive_missing_model_facts():
    from app.extraction import numeric_facts
    from app.schemas import Segment

    facts = numeric_facts(
        [
            Segment(
                start=0, end=10, text="Загрузка 65%. Потери 12%. Готовность 40%. У нас 7 площадок."
            )
        ]
    )
    assert len(facts) == 4
    assert all(any(number in f.indicator for f in facts) for number in ("65%", "12%", "40%", "7"))
