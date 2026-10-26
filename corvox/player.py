"""Play one job: synthesize chunk N+1 while chunk N plays, stop on cancel or the stop key."""

import queue
import threading

from corvox import audio, clean, engines, paths, spool

DONE = object()


def play_job(job: dict) -> None:
    gen = job["gen"]
    stop_key = audio.key_code(job.get("stop_key", "esc"))
    abort = threading.Event()

    def cancelled() -> bool:
        if abort.is_set():
            return True
        if audio.key_down(stop_key):
            spool.stop()
        if spool.generation(default=gen) != gen:
            abort.set()
        return abort.is_set()

    ready: queue.Queue = queue.Queue(maxsize=2)
    base = paths.cache_dir() / str(job["id"])

    def offer(item) -> None:
        while not abort.is_set():
            try:
                ready.put(item, timeout=0.1)
                return
            except queue.Full:
                pass

    def produce() -> None:
        synth = engines.Synth(job)
        for i, part in enumerate(clean.chunk(job["text"])):
            if abort.is_set():
                break
            try:
                offer(synth.render(part, base.with_name(f"{base.name}-{i}")))
            except Exception as e:
                paths.log(f"synthesis failed on chunk {i}: {type(e).__name__}: {e}")
                abort.set()
        offer(DONE)

    producer = threading.Thread(target=produce, daemon=True)
    producer.start()
    try:
        while not cancelled():
            try:
                item = ready.get(timeout=audio.POLL)
            except queue.Empty:
                if not producer.is_alive() and ready.empty():
                    break
                continue
            if item is DONE:
                break
            try:
                if not audio.play(item, cancelled):
                    break
            finally:
                item.unlink(missing_ok=True)
    finally:
        abort.set()
        producer.join(timeout=30)
        for leftover in paths.cache_dir().glob(f"{base.name}-*"):
            leftover.unlink(missing_ok=True)
