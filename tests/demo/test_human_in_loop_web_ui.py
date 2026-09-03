from pathlib import Path


HTML_PATH = Path("demo/static/web_ui.html")


def test_web_ui_contains_bounded_question_dialog_controls() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")

    assert 'id="interaction-dialog"' in html
    assert 'id="question-prev"' in html
    assert 'id="question-next"' in html
    assert 'id="question-counter"' in html
    assert 'id="answer-options"' in html
    assert 'id="custom-answer-input"' in html
    assert 'id="custom-answer-form"' in html


def test_web_ui_renders_recommended_options_and_submits_by_question_id() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")

    assert 'badge.textContent="推荐"' in html
    assert "option.recommended" in html
    assert "question.question_id" in html
    assert 'fetch("/tasks/input"' in html
    assert "questionCursorByTask" in html


def test_main_task_composer_no_longer_answers_pending_question_implicitly() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")
    submit_function = html.split(
        "async function submitInstruction", 1
    )[1].split("function connectTaskEvents", 1)[0]

    assert 'fetch("/tasks"' in submit_function
    assert 'fetch("/tasks/input"' not in submit_function
