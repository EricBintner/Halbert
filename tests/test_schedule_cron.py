from cerebric_core.cerebric_core.tools.schedule_cron import ScheduleCron


def test_upsert_block_appends_when_missing():
    sc = ScheduleCron()
    before = "MAILTO=me@example.com\n"
    header = "# backup"
    line = "0 2 * * * /usr/local/bin/backup"
    after, changed = sc._upsert_block(before, header, line)
    assert changed is True
    assert header in after
    assert line in after
    assert after.endswith("\n")


def test_upsert_block_updates_when_present():
    sc = ScheduleCron()
    before = "# backup\n0 1 * * * /old\n# other\n* * * * * /something\n"
    header = "# backup"
    line = "0 2 * * * /usr/local/bin/backup"
    after, changed = sc._upsert_block(before, header, line)
    assert changed is True
    # header preserved, line updated
    assert after.splitlines()[0].strip() == header
    assert after.splitlines()[1].strip() == line


def test_unified_diff_contains_headers():
    sc = ScheduleCron()
    d = sc._unified_diff("a\n", "b\n")
    assert "--- crontab (before)" in d
    assert "+++ crontab (after)" in d
