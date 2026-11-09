from test.bases import WorldTestBase


def setup_multiworld(*args, **kwargs):
    """Historical scenarios keep their explicit boxes-off starting profile.

    Count scenarios use item_box_count and exercise the new defaults directly.
    """
    from test.general import setup_multiworld as setup
    def profile(raw):
        options = dict(raw or {})
        if "item_box_count" not in options:
            options.setdefault("box_locations", False)
        return options
    raw = kwargs.get("options")
    if isinstance(raw, list):
        kwargs["options"] = [profile(option) if world.game == "Crash Team Racing" else option
                             for world, option in zip(args[0], raw)]
    else:
        kwargs["options"] = profile(raw)
    return setup(*args, **kwargs)


class CTRTestBase(WorldTestBase):
    game = "Crash Team Racing"
    options = {"box_locations": False}
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        from .plan_options import plan_options
        if "options" in cls.__dict__:
            cls.options = plan_options(cls.options)
