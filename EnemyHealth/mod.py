"""Enemy HP numbers on the game's own combat health bars."""
import logging
import math
import time

from expedition33 import RuntimeQueryError
from expedition33.catalog import capture_matching
from expedition33.management import ModDefinition
from expedition33.values import capture_selected_values, read_values_many, read_values_many_with_references

BAR = 'WBP_CharacterHealthBar_C'
ENEMY = 'BP_jRPG_Enemy_Battle_Base_C'


def fields(values):
    if values.errors:
        raise RuntimeQueryError('Health-bar observation changed; waiting for a fresh observation')
    return {key[1]: value for key, value in values.values.items()}


def hp_text(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        return ''
    return f'{max(0, math.ceil(value)):,} HP'


def identity(obj):
    return obj.index, obj.serial, obj.address


def is_enemy(catalog, stats):
    actor = catalog.by_index.get(stats.outer_index)
    return actor is not None and any(
        catalog.classes[index].name == ENEMY for index in catalog.ancestors(actor.class_index))


def may_prepare_bars(state):
    # Bind during the battle intro, once actual enemy stats/widgets exist.
    # Waiting for IsBattleInitialized postpones construction until combat opens.
    return state.get('HasBattleStartedEndFlow') is False


def observe_bars(pid):
    catalog = capture_matching(pid, classes=(BAR, 'AC_jRPG_BattleManager_C'))
    managers = [o for o in catalog.select('AC_jRPG_BattleManager_C')
                if not o.object_flags & 0x10 and ':PersistentLevel.' in catalog.path_name(o)]
    active = False
    for row in read_values_many(catalog, managers,
            fields=('IsBattleInitialized', 'HasBattleStartedEndFlow')).values():
        state = fields(row)
        active |= may_prepare_bars(state)
    wanted = {}
    if active:
        bars = [o for o in catalog.select(BAR) if not o.object_flags & 0x10
                and catalog.path_name(o).startswith('/Engine/Transient.')]
        values, catalog = read_values_many_with_references(catalog, bars,
            fields=('CharacterBattleStats', 'ProgressBar_HP', 'WidgetTree'))
        for bar in bars:
            row = fields(values[bar.index])
            stats = row.get('CharacterBattleStats')
            if stats is not None and is_enemy(catalog, stats) and row.get('ProgressBar_HP') and row.get('WidgetTree'):
                wanted[identity(bar)] = (bar, row)
    return catalog, wanted


class BarObserver:
    """Worker-owned read-only discovery; never receives a Session or widget owner."""
    def __init__(self, pid):
        from expedition33._reader import ReadBatch
        self.pid = pid
        self.reader = ReadBatch(pid, share=True)
        self.reader.warm()

    def observe(self):
        with self.reader.bind():
            return observe_bars(self.pid)

    def close(self):
        self.reader.close()


class Mod:
    def __init__(self):
        self.session = None
        self.labels = {}
        self.next_discovery = self.next_values = 0.
        self.stopped = False
        self.error = None
        self.definitions = None
        self.planning = None
        self.timings = []
        self.reader = None
        self.monitor = None
        self.discovery_sequence = 0
        self.poll_gaps = []
        self.last_poll = None
        self.update_ms = []
        self.update_gaps = []
        self.last_update = None

    def management(self):
        return ModDefinition('sdk.enemy-health', 'Enemy HP', version='0.1.4',
            description='Current HP on normal enemy and boss health bars. Follows the original bar visibility. No combat or save changes.')

    def enable(self, session):
        self.session = session
        from .ui import prepare_definitions, prepare_planning
        # Read reusable class/function/enum metadata before any combat bars exist.
        from expedition33._reader import ReadBatch
        self.reader = ReadBatch(session.pid, share=True)
        self.reader.warm()
        with self.reader.bind():
            self.definitions = prepare_definitions(session.pid)
            self.planning = prepare_planning(session, self.definitions)
        from expedition33.admission_monitor import ReadOnlyAdmissionMonitor
        self.monitor = ReadOnlyAdmissionMonitor(lambda pid=session.pid: BarObserver(pid), interval=.35, max_age=2.)
        self.discovery_sequence = 0
        self.stopped = False
        self.error = None
        self.next_discovery = self.next_values = 0.

    def _discover(self):
        observation = self.monitor.snapshot()
        if observation is None or observation.sequence == self.discovery_sequence:
            return
        self.discovery_sequence = observation.sequence
        catalog, wanted = observation.admission
        for key in tuple(self.labels):
            if key not in wanted:
                if self.labels[key].close():
                    del self.labels[key]
        for key, (bar, row) in wanted.items():
            old = self.labels.get(key)
            if old is not None and (not old.ready or identity(old.stats) != identity(row['CharacterBattleStats'])):
                if not old.close():
                    continue
                del self.labels[key]
            if key not in self.labels:
                from .ui import HealthLabel
                owner = HealthLabel(self.session, bar, row, self.definitions, self.planning)
                # Journal before construction so a partial creation is still cleaned up.
                self.labels[key] = owner
                try:
                    started = time.perf_counter()
                    owner.build(catalog)
                    self.planning = owner.planner.observations()
                    self.timings.append(round((time.perf_counter()-started)*1000, 1))
                    self.timings[:] = self.timings[-24:]
                    # Show this enemy immediately, rather than leaving every
                    # label blank until the entire encounter has been built.
                    self._update()
                except RuntimeQueryError:
                    if owner.uncertain:
                        raise RuntimeError('Health label construction outcome is unknown')
                    if owner.close():
                        del self.labels[key]
                    raise
        self.catalog = catalog

    def _update(self):
        if not self.labels:
            return
        owners = [owner for owner in self.labels.values() if owner.ready]
        if not owners:
            return
        objects = {o.index: o for label in owners for o in (label.stats, label.progress)}
        _, values = capture_selected_values(self.session.pid,
            tuple(identity(o) for o in objects.values()),
            fields=('CurrentHP', 'Visibility', 'RenderOpacity'), references=True)
        for owner in owners:
            hp = fields(values[owner.stats.index]).get('CurrentHP')
            bar = fields(values[owner.progress.index])
            owner.update(hp_text(hp), bar['Visibility'], bar['RenderOpacity'])

    def poll(self):
        self._poll(discovery=True)

    def poll_fast(self):
        self._poll(discovery=False)

    def _poll(self, *, discovery):
        if self.session is None or self.stopped:
            return
        now = time.monotonic()
        if self.last_poll is not None:
            self.poll_gaps.append(round((now-self.last_poll)*1000, 1))
            self.poll_gaps[:] = self.poll_gaps[-120:]
        self.last_poll = now
        try:
            if self.reader is None:
                from expedition33._reader import ReadBatch
                self.reader = ReadBatch(self.session.pid, share=True)
                self.reader.warm()
            with self.reader.bind():
                if discovery and now >= self.next_discovery:
                    self.next_discovery = now + .05
                    self._discover()
                if now >= self.next_values:
                    self.next_values = now + .05
                    if self.last_update is not None:
                        self.update_gaps.append(round((now-self.last_update)*1000, 1))
                        self.update_gaps[:] = self.update_gaps[-120:]
                    self.last_update = now
                    started = time.perf_counter()
                    self._update()
                    self.update_ms.append(round((time.perf_counter()-started)*1000, 1))
                    self.update_ms[:] = self.update_ms[-120:]
                    self.error = None
        except RuntimeQueryError as error:
            # A failed worker is terminal. Start a distinct fresh observation on
            # a later poll, never replay the failed query or any mutation.
            if self.reader is not None and self.reader._closed:
                self.reader = None
            self.next_discovery = now + .2
            self.error = str(error)
        except Exception as error:
            self.error = str(error)
            self.stopped = True
            logging.getLogger(__name__).exception('Enemy HP stopped; cleanup remains owned')
            self._close()

    def _close(self):
        monitor_closed = True
        if self.monitor is not None:
            monitor_closed = self.monitor.close()
            if monitor_closed:
                self.monitor = None
        if self.reader is not None:
            self.reader.close()
            self.reader = None
        for key in tuple(self.labels):
            if self.labels[key].close():
                del self.labels[key]
        return not self.labels and monitor_closed

    def revoke_world(self, context):
        self.stopped = True

    def begin_world_retirement(self, context):
        return 'ack' if self._close() else 'pending'

    def poll_world_retirement(self, context):
        return 'ack' if self._close() else 'pending'

    def prepare_disable(self):
        self.stopped = True
        return self._close()

    def disable(self):
        self.stopped = True
        if not self._close():
            from expedition33.mods import ModDisablePending
            raise ModDisablePending('Enemy HP labels are awaiting collector release')
        self.session = None
