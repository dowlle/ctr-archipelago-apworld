from test.bases import WorldTestBase


class CTRTestBase(WorldTestBase):
    game = "Crash Team Racing"
    # The start bootstrap moves a few pool items onto checks, so a test that counts
    # the pool wants the same seed on every run.
    seed = 20261031

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        from .plan_options import plan_options
        if "options" in cls.__dict__:
            cls.options = plan_options(cls.options)
