"""A retained text child of the original progress bar's overlay; no viewport or input owner."""
from expedition33._scope import SessionScope
from expedition33.catalog import capture_matching
from expedition33.values import read_values_with_references
from expedition33.widgets import widget_definition_names


def prepare_definitions(pid):
    names = widget_definition_names(('GameplayStatics', 'CommonTextBlock',
        'CTS_B1_SmallLine_Outline_C', 'Overlay', 'OverlaySlot', 'Widget', 'TextBlock',
        'TextLayoutWidget')) + ('SpawnObject', 'AddChildToOverlay', 'SetStyle', 'SetText',
        'SetRenderScale', 'SetVisibility', 'SetRenderOpacity', 'SetJustification',
        'SetHorizontalAlignment', 'SetVerticalAlignment', 'RemoveFromParent',
        'SetPadding', 'SetRenderTransformPivot', 'SetRenderTranslation', 'Margin',
        'ESlateVisibility', 'Vector2D', 'EHorizontalAlignment', 'EVerticalAlignment', 'ETextJustify')
    catalog = capture_matching(pid, names=names)
    from expedition33.enums import describe_enums
    enum_names = ('ESlateVisibility', 'EHorizontalAlignment', 'EVerticalAlignment', 'ETextJustify')
    enum_objects = [next(o for o in catalog.objects if o.name == n and o.class_name == 'Enum') for n in enum_names]
    descriptors = describe_enums(catalog, enum_objects)
    enums = {o.name: descriptors[o.index] for o in enum_objects}
    return catalog, enums


def prepare_planning(session, definitions):
    """Read invocation schemas before combat; prepare only, never dispatch."""
    catalog, enums = definitions
    planner = session.invocation_planner(catalog=catalog, selected_results=True)
    def obj(name):
        return next(o for o in catalog.objects if o.name == 'Default__'+name)
    def cls(name):
        return catalog.by_index[catalog.find_class(name).index]
    visibility = enums['ESlateVisibility']
    invisible = visibility.value(next(m.name for m in visibility.members if m.value == 3))
    text = obj('CommonTextBlock')
    slot = obj('OverlaySlot')
    calls = (
        (obj('GameplayStatics'), 'GameplayStatics', 'SpawnObject', {'ObjectClass':cls('CommonTextBlock'), 'Outer':obj('GameplayStatics')}),
        (text, 'CommonTextBlock', 'SetStyle', {'InStyle':cls('CTS_B1_SmallLine_Outline_C')}),
        (text, 'Widget', 'SetRenderTransformPivot', {'Pivot':{'X':0., 'Y':0.}}),
        (text, 'Widget', 'SetRenderScale', {'Scale':{'X':.85, 'Y':.85}}),
        (text, 'Widget', 'SetRenderTranslation', {'Translation':{'X':-64., 'Y':-50.}}),
        (text, 'Widget', 'SetVisibility', {'InVisibility':invisible}),
        (text, 'Widget', 'SetRenderOpacity', {'InOpacity':1.}),
        (text, 'TextLayoutWidget', 'SetJustification', {'InJustification':0}),
        (text, 'TextBlock', 'SetText', {'InText':'0 HP'}),
        (obj('Overlay'), 'Overlay', 'AddChildToOverlay', {'Content':text}),
        (slot, 'OverlaySlot', 'SetHorizontalAlignment', {'InHorizontalAlignment':1}),
        (slot, 'OverlaySlot', 'SetVerticalAlignment', {'InVerticalAlignment':1}),
        (slot, 'OverlaySlot', 'SetPadding', {'InPadding':{'Left':0., 'Top':-34., 'Right':0., 'Bottom':0.}}),
        (text, 'Widget', 'RemoveFromParent', {}),
    )
    try:
        for target, owner, name, args in calls:
            index=catalog.find_class(owner).index
            function=next(o for o in catalog.objects if o.class_name=='Function' and o.outer_index==index and o.name==name)
            planner.prepare(target, function, **args)
        return planner.observations()
    finally:
        planner.close()


class HealthLabel:
    def __init__(self, session, bar, row, definitions, planning=None):
        self.definitions = definitions
        self.planning = planning
        self.scope = SessionScope(session)
        self.bar = bar
        self.stats = row['CharacterBattleStats']
        self.progress = row['ProgressBar_HP']
        self.tree = row['WidgetTree']
        self.label = None
        self.planner = None
        self.uncertain = False
        self.last = None
        self.ready = False

    def _function(self, owner, name):
        index = self.catalog.find_class(owner).index
        rows = [o for o in self.catalog.objects if o.class_name == 'Function'
                and o.outer_index == index and o.name == name]
        if len(rows) != 1:
            raise RuntimeError('Missing or ambiguous health label function: '+owner+'.'+name)
        return rows[0]

    def _call(self, obj, owner, name, **args):
        if self.uncertain:
            raise RuntimeError('Health label has an unacknowledged mutation')
        call = self.planner.prepare(obj, self._function(owner, name), **args)
        self.uncertain = True
        from expedition33.invocation import InvocationError
        try:
            result = call.invoke(refresh_from_result=True)
        except InvocationError as error:
            if error.outcome == 'not_dispatched':
                self.uncertain = False
            raise
        self.uncertain = False
        self.catalog = self.planner._catalog
        return result

    def _setters(self, rows):
        from expedition33 import _ui_batch
        if (any(owner == 'OverlaySlot' for _, owner, _, _ in rows)
                or not _ui_batch.extended_layout_available(self.scope._session)):
            for obj, owner, name, args in rows:
                with self._call(obj, owner, name, **args): pass
            return
        if self.uncertain:
            raise RuntimeError('Health label has an unacknowledged mutation')
        calls = [self.planner.prepare(obj, self._function(owner, name), **args)
                 for obj, owner, name, args in rows]
        self.uncertain = True
        _ui_batch.invoke_setters(self.scope, calls)
        self.uncertain = False

    def _enum(self, name, value):
        descriptor = self.enums[name]
        member = next(m for m in descriptor.members if m.value == value and not m.name.endswith('_MAX'))
        return descriptor.value(member.name)

    def build(self, observations):
        self.catalog = self.definitions[0].with_observations(observations)
        self.enums = self.definitions[1]
        pv, self.catalog = read_values_with_references(self.catalog, self.progress, fields=('Slot',))
        slot = next(value for key, value in pv.values.items() if key[1] == 'Slot')
        # UPanelWidget owns its UPanelSlot; the reference closure includes that
        # outer identity. Native dispatch still validates this exact parent.
        parent = self.catalog.by_index[slot.outer_index]
        if parent.class_name != 'Overlay':
            raise RuntimeError('Unrecognized enemy health-bar layout')
        if self.planning is None:
            self.planner = self.scope.invocation_planner(catalog=self.catalog, selected_results=True)
        else:
            self.planner = self.scope.invocation_planner(observations=self.planning, selected_results=True)
            self.planner.adopt_observations(self.catalog)
            self.catalog = self.planner._catalog
        default = next(o for o in self.catalog.objects if o.name == 'Default__GameplayStatics')
        def cls(name): return self.catalog.by_index[self.catalog.find_class(name).index]
        result = self._call(default, 'GameplayStatics', 'SpawnObject',
                            ObjectClass=cls('CommonTextBlock'), Outer=self.tree)
        self.label = result.return_value
        # The result lease remains tracked by this child scope until removal.
        self._setters((
            (self.label, 'CommonTextBlock', 'SetStyle', {'InStyle':cls('CTS_B1_SmallLine_Outline_C')}),
            (self.label, 'Widget', 'SetRenderTransformPivot', {'Pivot':{'X':0., 'Y':0.}}),
            (self.label, 'Widget', 'SetRenderScale', {'Scale':{'X':.85, 'Y':.85}}),
            (self.label, 'Widget', 'SetVisibility', {'InVisibility':self._enum('ESlateVisibility', 3)}),
            (self.label, 'TextLayoutWidget', 'SetJustification', {'InJustification':0}),
        ))
        # The default fill slot and left text justification align the number.
        # Translate the label instead of mutating three OverlaySlot properties.
        with self._call(self.label, 'Widget', 'SetRenderTranslation', Translation={'X':-64., 'Y':-50.}): pass
        self._call(parent, 'Overlay', 'AddChildToOverlay', Content=self.label)
        self.ready = True

    def update(self, text, visibility, opacity):
        state = (text, visibility, opacity)
        if state == self.last:
            return
        if self.last is None or text != self.last[0]:
            with self._call(self.label, 'TextBlock', 'SetText', InText=text): pass
        # Preserve the original progress bar's hidden/collapsed state, but never
        # make our label intercept clicks when the bar itself is hit-testable.
        shown = visibility if visibility in (1, 2) else 3
        if self.last is None or visibility != self.last[1]:
            with self._call(self.label, 'Widget', 'SetVisibility', InVisibility=self._enum('ESlateVisibility', shown)): pass
        if self.last is None or opacity != self.last[2]:
            with self._call(self.label, 'Widget', 'SetRenderOpacity', InOpacity=float(opacity)): pass
        self.last = state

    def close(self):
        self.ready = False
        if self.label is not None:
            with self._call(self.label, 'Widget', 'RemoveFromParent'): pass
            self.label = None
        if self.planner is not None:
            self.planner.close()
            self.planner = None
        from expedition33._retired_tracking import close_lease_only_scope
        return close_lease_only_scope(self.scope)
