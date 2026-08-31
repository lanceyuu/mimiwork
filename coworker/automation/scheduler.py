"""The scheduler loop — runs in the always-on server.

Policy (agreed): **run-once-catch-up** for runs missed while down (due tasks fire once on
startup, then resume), and **skip-on-overlap** (don't stack a run if the previous is still
going). The actual execution is injected as `runner(task, trigger) -> TaskRun` so this stays
independent of the engine/manager.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Optional

from .models import ScheduledTask, TaskRun
from .store import TaskStore, _epoch_now

logger = logging.getLogger("coworker.automation")

Runner = Callable[[ScheduledTask, str], Awaitable[TaskRun]]


class Scheduler:
    def __init__(
        self,
        store: TaskStore,
        runner: Runner,
        *,
        tick_seconds: float = 30.0,
        extra_tick: Optional[Callable[[], Awaitable[None]]] = None,
    ) -> None:
        self.store = store
        self.runner = runner
        self.tick_seconds = tick_seconds
        # An extra per-tick coroutine (self-wake resumption: resume sessions whose wakes are due).
        self.extra_tick = extra_tick
        self._task: Optional[asyncio.Task] = None
        self._running_ids: set[str] = set()  # overlap guard
        self._spawned: set[asyncio.Task] = set()  # keep spawned runs referenced

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        # In-flight runs died with the loop before they were spawned; keep that shutdown
        # contract now that they're independent tasks (a suspended run must not outlive us).
        for spawned in list(self._spawned):
            spawned.cancel()
            try:
                await spawned
            except asyncio.CancelledError:
                pass
        self._spawned.clear()

    async def _loop(self) -> None:
        # First pass = run-once-catch-up for anything missed while the server was down.
        try:
            await self._tick(trigger="catchup")
        except Exception:
            logger.exception("scheduler catch-up failed")
        while True:
            await asyncio.sleep(self.tick_seconds)
            try:
                await self._tick(trigger="schedule")
            except Exception:
                logger.exception("scheduler tick failed")

    async def _tick(self, *, trigger: str) -> None:
        for task in self.store.due():
            # Spawn, don't await: a run can suspend on a parked approval (standing
            # scoped approvals, §25) and one blocked automation must never stall the
            # scheduler loop, other due tasks, or self-wake resumption.
            #
            # Claim HERE, synchronously, not inside run_task: the spawned coroutine's
            # first step can be delayed arbitrarily under load, and a claim taken only
            # at that first step leaves a window where a tick during a parked run
            # spawns a second claim that starts after the first completes — and re-runs
            # a task that is no longer due. Concretely: approve a parked automation,
            # it runs twice (reproduced on CI, 2026-08-19).
            if task.id in self._running_ids:
                logger.info("skipping %s — previous run still going", task.id)
                continue
            self._running_ids.add(task.id)
            spawned = asyncio.create_task(
                self.run_task(task, trigger=trigger, _claimed=True)
            )
            self._spawned.add(spawned)
            spawned.add_done_callback(self._spawned.discard)
        if self.extra_tick is not None:
            try:
                await self.extra_tick()
            except Exception:
                logger.exception("scheduler extra_tick (wake resume) failed")

    async def run_task(
        self, task: ScheduledTask, *, trigger: str, _claimed: bool = False
    ) -> Optional[TaskRun]:
        # _claimed=True means _tick already took the claim synchronously (see above).
        # Direct callers still get the guard here.
        if not _claimed:
            if task.id in self._running_ids:  # skip-on-overlap
                logger.info("skipping %s — previous run still going", task.id)
                return None
            self._running_ids.add(task.id)
        run: Optional[TaskRun] = None
        try:
            run = await self.runner(task, trigger)
        except Exception as exc:
            logger.exception("task %s run failed", task.id)
            run = TaskRun(
                task_id=task.id, status="error", error=str(exc), trigger=trigger
            )
            # Recording the failure must not COST us the reschedule below. When the
            # host is out of file descriptors every run fails here AND this write
            # fails too, and an escaping exception used to skip the save — so
            # next_run never advanced, the task came due again on the next 30s tick,
            # and each retry leaked more descriptors. Hundreds of sessions, all
            # "[Errno 24] Too many open files" (owner-hit 2026-08-31).
            try:
                self.store.add_run(run)
            except Exception:
                logger.exception("could not record the failed run for %s", task.id)
        finally:
            self._running_ids.discard(task.id)
            # Advance the task (run_count/last_run) → save recomputes next_run.
            # In `finally` because a schedule that cannot move forward is the one
            # failure that repeats itself: whatever went wrong, this task must not
            # still be due when the next tick comes round.
            try:
                fresh = self.store.get(task.id)
                if fresh is not None:
                    fresh.run_count += 1
                    fresh.last_run = run.started_at if run else _epoch_now()
                    fresh.last_status = run.status if run else "error"
                    self.store.save(fresh)
            except Exception:
                logger.exception("could not advance the schedule for %s", task.id)
        return run
