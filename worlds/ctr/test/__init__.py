from test.bases import WorldTestBase


def setup_multiworld(*args, **kwargs):
    """Historical scenarios keep their explicit boxes-off starting profile.

    Count scenarios use item_box_count and exercise the new defaults directly.
    """
    from test.general import setup_multiworld as setup
    options = dict(kwargs.get("options") or {})
    if "item_box_count" not in options:
        options.setdefault("box_locations", False)
    kwargs["options"] = options
    return setup(*args, **kwargs)


class CTRTestBase(WorldTestBase):
    game = "Crash Team Racing"
    options = {"box_locations": False}
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        from .plan_options import plan_options
        if "options" in cls.__dict__:
            cls.options = plan_options(cls.options)
