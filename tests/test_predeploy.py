from unittest import mock

from django.core.management import call_command


def test_predeploy_migrates_then_creates_the_cache_table():
    with mock.patch("apps.core.management.commands.predeploy.call_command") as inner:
        call_command("predeploy", verbosity=0)

    assert [c.args[0] for c in inner.call_args_list] == ["migrate", "createcachetable"]
    assert inner.call_args_list[0].kwargs["interactive"] is False
