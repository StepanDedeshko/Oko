from dataclasses import dataclass


@dataclass(frozen=True)
class DutyCallbackToken:
    run_id: int
    stage_id: int
    stage: str = ""


class DutyFlowGuard:
    """Small state machine guarding duty-flow runs, stages and stage actions."""

    def __init__(self, logger=None):
        self.logger = logger
        self.run_id = 0
        self.stage_id = 0
        self.running = False
        self.cancelling = False
        self.current_stage = None
        self.stage_action_in_progress = False
        self.stage_action_id = 0

    def start_flow(self):
        if self.running:
            if self.logger:
                self.logger.info("Duty flow duplicate start ignored: run_id=%s", self.run_id)
            return None
        self.run_id += 1
        self.stage_id += 1
        self.running = True
        self.cancelling = False
        self.current_stage = None
        self.stage_action_in_progress = False
        self.stage_action_id = 0
        if self.logger:
            self.logger.info("Duty flow started: run_id=%s", self.run_id)
        return self.run_id

    def start_stage(self, stage):
        if not self.running:
            return None
        self.stage_id += 1
        self.current_stage = stage
        self.stage_action_in_progress = False
        if self.logger:
            self.logger.info(
                "Duty stage started: run_id=%s, stage_id=%s, stage=%s",
                self.run_id,
                self.stage_id,
                stage,
            )
            self.logger.info(
                "Duty stage action reset: run_id=%s, stage_id=%s, next_stage=%s",
                self.run_id,
                self.stage_id,
                stage,
            )
        return self.token()

    def token(self):
        return DutyCallbackToken(self.run_id, self.stage_id, self.current_stage or "")

    def is_current(self, run_id, stage_id=None, callback=""):
        if not self.running:
            return False
        if run_id != self.run_id:
            if self.logger:
                self.logger.info(
                    "Duty callback ignored for stale run: callback=%s, callback_run_id=%s, current_run_id=%s",
                    callback,
                    run_id,
                    self.run_id,
                )
            return False
        if stage_id is not None and stage_id != self.stage_id:
            if self.logger:
                self.logger.info(
                    "Duty callback ignored for stale stage: callback=%s, callback_stage_id=%s, current_stage_id=%s",
                    callback,
                    stage_id,
                    self.stage_id,
                )
            return False
        return True

    def start_action(self, action):
        if not self.running:
            return False
        if self.stage_action_in_progress:
            if self.logger:
                self.logger.info(
                    "Duty stage action ignored duplicate: run_id=%s, stage_id=%s, action=%s",
                    self.run_id,
                    self.stage_id,
                    action,
                )
            return False
        self.stage_action_in_progress = True
        self.stage_action_id += 1
        if self.logger:
            self.logger.info(
                "Duty stage action started: run_id=%s, stage_id=%s, action=%s",
                self.run_id,
                self.stage_id,
                action,
            )
        return True

    def reset_action(self, next_stage=""):
        self.stage_action_in_progress = False
        if self.logger:
            self.logger.info(
                "Duty stage action reset: run_id=%s, stage_id=%s, next_stage=%s",
                self.run_id,
                self.stage_id,
                next_stage,
            )

    def finish_flow(self):
        finished_run = self.run_id
        self.running = False
        self.cancelling = False
        self.current_stage = None
        self.stage_action_in_progress = False
        if self.logger:
            self.logger.info("Duty flow finished: run_id=%s", finished_run)

    def cancel_flow(self, reason=""):
        cancelled_run = self.run_id
        self.cancelling = True
        self.running = False
        self.run_id += 1
        self.stage_id += 1
        self.current_stage = None
        self.stage_action_in_progress = False
        self.cancelling = False
        if self.logger:
            self.logger.info("Duty flow cancelled: run_id=%s, reason=%s", cancelled_run, reason)
