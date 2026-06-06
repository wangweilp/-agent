from src.core.import_worker import ImportJob, ImportWorker


class _History:
    def __init__(self) -> None:
        self.jobs = []

    def update_job(self, job: ImportJob) -> None:
        self.jobs.append(job.status)


class _Writer:
    def __init__(self) -> None:
        self.tasks = []

    def enqueue(self, task) -> None:
        self.tasks.append(task)


def test_import_worker_uses_file_type_mapping_for_default_memory_type(tmp_path):
    writer = _Writer()
    worker = ImportWorker(object(), memory_writer=writer, dead_letter_dir=str(tmp_path))
    worker._history = _History()
    worker._parse_sources = lambda job: [{"content": "hello", "entities": []}]

    job = ImportJob(file_type="markdown")
    worker._process_job(job, sqlite=None, chroma=None, embedding=None)

    assert job.status == "completed"
    assert job.memories_created == 1
    assert len(writer.tasks) == 1


def test_import_worker_resumes_from_next_unprocessed_chunk(tmp_path):
    writer = _Writer()
    worker = ImportWorker(object(), memory_writer=writer, dead_letter_dir=str(tmp_path))
    worker._history = _History()
    worker._parse_sources = lambda job: [
        {"content": "already processed", "entities": []},
        {"content": "next chunk", "entities": []},
    ]

    job = ImportJob(file_type="txt")
    worker._progress[job.id] = 1
    worker._process_job(job, sqlite=None, chroma=None, embedding=None)

    assert job.status == "completed"
    assert job.processed_chunks == 2
    assert len(writer.tasks) == 1
    assert writer.tasks[0].arguments["content"] == "next chunk"
