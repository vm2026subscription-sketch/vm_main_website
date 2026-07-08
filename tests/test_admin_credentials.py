from app import _get_admin_credentials


def test_admin_credentials_include_requested_defaults():
    email, password = _get_admin_credentials()
    assert email == "admin123@gmail.com"
    assert password == "vm@2026"
