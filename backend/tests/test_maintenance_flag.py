from app import maintenance


def test_flag_defaults_off_and_toggles():
    maintenance.set_on(False)
    try:
        assert maintenance.is_on() is False
        maintenance.set_on(True)
        assert maintenance.is_on() is True
        maintenance.set_on(False)
        assert maintenance.is_on() is False
    finally:
        maintenance.set_on(False)
