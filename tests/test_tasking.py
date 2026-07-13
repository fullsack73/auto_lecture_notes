from lecture_auto.tasking import CancellationToken, TaskCancelledError, report_progress


def test_cancellation_token_raises_after_cancel() -> None:
    token = CancellationToken()
    token.raise_if_cancelled()
    token.cancel()
    try:
        token.raise_if_cancelled()
    except TaskCancelledError:
        pass
    else:
        raise AssertionError("Expected TaskCancelledError")


def test_report_progress_builds_event() -> None:
    events = []
    report_progress(events.append, job_id="job", session_id="s1", stage="work", completed=1, total=2, message="Working")
    assert events[0].job_id == "job"
    assert events[0].completed == 1
