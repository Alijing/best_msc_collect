import pytest

from app.core.task_store import TaskStore


@pytest.mark.asyncio
async def test_progress_does_not_carry_chapter_body():
    store = TaskStore()
    await store.create("t1", {"status": "running", "chapter_count": 0})
    await store.update(
        "t1",
        chapter_count=1,
        chapters=[{
            "order": 1,
            "title": "第一章",
            "url": "https://example.com/1",
            "content": "SECRET",
        }],
    )

    progress = await store.get("t1")
    assert progress is not None
    assert progress["chapter_count"] == 1
    assert "SECRET" not in str(progress)
    assert "chapters" not in progress

    light = await store.get_chapter_list("t1", with_content=False)
    assert light[0]["title"] == "第一章"
    assert "content" not in light[0]


@pytest.mark.asyncio
async def test_result_body_is_separate_from_status():
    store = TaskStore()
    await store.create("t1", {"status": "running"})
    body = "正文" * 50
    await store.update("t1", result={
        "chapter_count": 1,
        "chapters": [{
            "order": 1,
            "title": "第一章",
            "url": "https://example.com/1",
            "content": body,
            "content_pages": 2,
            "content_error": None,
        }],
    })

    progress = await store.get("t1")
    assert progress is not None
    assert progress["result_ready"] is True
    assert body not in str(progress)

    light = await store.get_chapter_list("t1", with_content=False)
    assert light[0]["content_pages"] == 2
    assert "content" not in light[0]

    full = await store.get_chapter_list("t1", with_content=True)
    assert full[0]["content"] == body


@pytest.mark.asyncio
async def test_chapter_page_reads_only_requested_body():
    store = TaskStore()
    await store.create("t", {"status": "running"})
    await store.update("t", result={"chapters": [
        {"order": 1, "title": "一", "url": "https://a/1", "content": "AAA"},
        {"order": 2, "title": "二", "url": "https://a/2", "content": "BBB"},
    ]})
    total, page = await store.get_chapter_page("t", 1, 1, True)
    assert total == 2
    assert len(page) == 1
    assert page[0]["content"] == "BBB"
    assert "AAA" not in str(page)


@pytest.mark.asyncio
async def test_deleted_task_ignores_later_writes():
    store = TaskStore()
    await store.create("t", {"status": "running"})
    await store.delete("t")
    await store.update("t", status="running", chapter_count=4, result={
        "chapters": [{"order": 1, "title": "甲", "url": "https://a", "content": "Z"}],
    })
    assert await store.get("t") is None
    assert await store.get_chapter_list("t", with_content=True) == []


@pytest.mark.asyncio
async def test_evict_drops_finished_task_not_running_one():
    store = TaskStore(max_tasks=1)
    await store.create("done", {"status": "completed"})
    await store.update("done", result={
        "chapters": [{"order": 1, "title": "甲", "url": "https://a", "content": "BODY"}],
    })
    assert (await store.get_chapter_list("done", with_content=True))[0]["content"] == "BODY"

    await store.create("run", {"status": "running"})
    assert await store.get("run") is not None
    assert await store.get("done") is None
    assert await store.get_chapter_list("done", with_content=True) == []
