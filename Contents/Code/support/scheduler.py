# coding=utf-8

import datetime
import logging
import traceback

from config import config

def parse_frequency(s):
    if s == "never" or s is None:
        return None, None
    kind, num, unit = s.split()
    return int(num), unit


class DefaultScheduler(object):
    queue_thread = None
    scheduler_thread = None
    running = False
    registry = None

    def __init__(self):
        self.queue_thread = None
        self.scheduler_thread = None
        self.running = False
        self.registry = []

        self.tasks = {}
        self.init_storage()

    def init_storage(self):
        if "tasks" not in Dict:
            Dict["tasks"] = {"queue": []}
            Dict.Save()

        if "queue" not in Dict["tasks"]:
            Dict["tasks"]["queue"] = []

    def get_task_data(self, name):
        if name not in Dict["tasks"]:
            raise NotImplementedError("Task missing! %s" % name)

        if "data" in Dict["tasks"][name]:
            return Dict["tasks"][name]["data"]

    def clear_task_data(self, name=None):
        if name is None:
            # full clean
            Log.Debug("Clearing previous task data")
            if Dict["tasks"]:
                for task_name in Dict["tasks"].keys():
                    if task_name == "queue":
                        Dict["tasks"][task_name] = []
                        continue

                    Dict["tasks"][task_name]["data"] = {}
                    Dict["tasks"][task_name]["running"] = False
                Dict.Save()
            return

        if name not in Dict["tasks"]:
            raise NotImplementedError("Task missing! %s" % name)

        Dict["tasks"][name]["data"] = {}
        Dict["tasks"][name]["running"] = False
        Dict.Save()
        Log.Debug("Task data cleared: %s", name)

    def register(self, task):
        self.registry.append(task)

    def setup_tasks(self):
        # discover tasks;
        self.tasks = {}
        for cls in self.registry:
            task = cls()
            try:
                task_frequency = Prefs["scheduler.tasks.%s.frequency" % task.name]
            except KeyError:
                task_frequency = getattr(task, "frequency", None)

            self.tasks[task.name] = {"task": task, "frequency": parse_frequency(task_frequency)}

    def run(self):
        self.running = True
        self.scheduler_thread = Thread.Create(self.scheduler_worker)
        self.queue_thread = Thread.Create(self.queue_worker)

    def stop(self):
        self.running = False

    def task(self, name):
        if name not in self.tasks:
            return None
        return self.tasks[name]["task"]

    def is_task_running(self, name):
        task = self.task(name)
        if task:
            return task.running

    def last_run(self, task):
        if task not in self.tasks:
            return None
        return self.tasks[task]["task"].last_run

    def next_run(self, task):
        if task not in self.tasks or not self.tasks[task]["task"].periodic:
            return None
        frequency_num, frequency_key = self.tasks[task]["frequency"]
        if not frequency_num:
            return None
        last = self.tasks[task]["task"].last_run
        use_date = last
        now = datetime.datetime.now()
        if not use_date:
            use_date = now
        return max(use_date + datetime.timedelta(**{frequency_key: frequency_num}), now)

    def run_task(self, name, *args, **kwargs):
        task = self.tasks[name]["task"]

        if task.running:
            Log.Debug("Scheduler: Not running %s, as it's currently running.", name)
            return False

        Log.Debug("Scheduler: Running task %s", name)
        try:
            task.prepare(*args, **kwargs)
            task.run()
        except Exception, e:
            Log.Error("Scheduler: Something went wrong when running %s: %s", name, traceback.format_exc())
        finally:
            try:
                task.post_run(Dict["tasks"][name]["data"])
            except:
                Log.Error("Scheduler: task.post_run failed for %s: %s", name, traceback.format_exc())
            Dict.Save()
            config.sync_cache()

    def dispatch_task(self, *args, **kwargs):
        if "queue" not in Dict["tasks"]:
            Dict["tasks"]["queue"] = []

        Dict["tasks"]["queue"].append((args, kwargs))

    def signal(self, name, *args, **kwargs):
        for task_name in self.tasks.keys():
            task = self.task(task_name)
            if not task:
                Log.Error("Scheduler: Task %s not found (?!)" % task_name)
                continue

            if not task.periodic:
                continue

            if task.running:
                Log.Debug("Scheduler: Sending signal %s to task %s (%s, %s)", name, task_name, args, kwargs)
                try:
                    status = task.signal(name, *args, **kwargs)
                except NotImplementedError:
                    Log.Debug("Scheduler: Signal ignored by %s", task_name)
                    continue
                if status:
                    Log.Debug("Scheduler: Signal accepted by %s", task_name)
                else:
                    Log.Debug("Scheduler: Signal not accepted by %s", task_name)
                continue
            Log.Debug("Scheduler: Not sending signal %s to task %s, because: not running", name, task_name)

    def queue_worker(self):
        Thread.Sleep(10.0)
        while 1:
            if not self.running:
                break

            # single dispatch requested?
            if Dict["tasks"]["queue"]:
                # work queue off
                queue = Dict["tasks"]["queue"][:]
                Dict["tasks"]["queue"] = []
                Dict.Save()
                for args, kwargs in queue:
                    Log.Debug("Queue: Dispatching single task: %s, %s", args, kwargs)
                    Thread.Create(self.run_task, True, *args, **kwargs)
                    Thread.Sleep(5.0)

            Thread.Sleep(1)

    def scheduler_worker(self):
        Thread.Sleep(10.0)
        while 1:
            if not self.running:
                break

            # scheduled tasks
            for name in self.tasks.keys():
                now = datetime.datetime.now()
                info = self.tasks.get(name)
                if not info:
                    Log.Error("Scheduler: Task %s not found (?!)" % name)
                    continue
                task = info["task"]

                if name not in Dict["tasks"] or not task.periodic:
                    continue

                if task.running:
                    continue

                frequency_num, frequency_key = info["frequency"]
                if not frequency_num:
                    continue

                # run legacy SARAM once
                if name == "SearchAllRecentlyAddedMissing" and ("hasRunLSARAM" not in Dict or not Dict["hasRunLSARAM"]):
                    task = self.tasks["LegacySearchAllRecentlyAddedMissing"]["task"]
                    task.last_run = None
                    name = "LegacySearchAllRecentlyAddedMissing"
                    Dict["hasRunLSARAM"] = True
                    Dict.Save()

                if not task.last_run or (task.last_run + datetime.timedelta(**{frequency_key: frequency_num}) <= now):
                    # fixme: scheduled tasks run synchronously. is this the best idea?
                    Thread.Create(self.run_task, True, name)
                    #Thread.Sleep(5.0)
                    #self.run_task(name)
                    Thread.Sleep(5.0)

            Thread.Sleep(1)


scheduler = DefaultScheduler()
