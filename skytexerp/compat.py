"""
Compatibility shims for framework/interpreter version mismatches.

Django 4.2.7 vs. Python 3.14
-----------------------------
`django.template.context.BaseContext.__copy__` (Django 4.2.7) copies itself
via `copy(super())` - an undocumented CPython trick to get a plain shallow
copy of the real (sub)class without re-entering that subclass's own
`__copy__` override and recursing.

Python 3.14 changed how `copy.copy()` handles a bound `super` proxy object,
breaking that trick everywhere Django copies a template Context. The most
visible symptom: every Django admin changelist page (the list view for any
registered model - Users, Fabrics, everything) crashes with:

    AttributeError: 'super' object has no attribute 'dicts' and no
    __dict__ for setting new attributes

This is a Django/Python version-compatibility bug, not an application bug -
regular (non-admin) pages are unaffected, since they don't happen to hit
this particular context-copying path.

`patch_template_context_copy()` replaces `BaseContext.__copy__` with an
equivalent implementation that doesn't rely on the broken `copy(super())`
trick: it creates a new instance of the real class via `__new__` (skipping
`__init__`, so no recursion), shallow-copies every instance attribute, then
rebinds `.dicts` to a fresh list - exactly what the original did. Context
subclasses (`Context`, `RequestContext`, `RenderContext`) don't need their
own patch: `Context.__copy__` already calls `super().__copy__()`, so it
picks up this fix automatically.

Remove this shim once the project's Django dependency is upgraded to a
version with native Python 3.14 support (check that the upstream ticket is
actually fixed there before removing).
"""


def patch_template_context_copy():
    from django.template.context import BaseContext

    def __copy__(self):
        duplicate = self.__class__.__new__(self.__class__)
        duplicate.__dict__.update(self.__dict__)
        duplicate.dicts = self.dicts[:]
        return duplicate

    BaseContext.__copy__ = __copy__
