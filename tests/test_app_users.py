import tempfile
import unittest
from pathlib import Path

from app.app_users import (
    ROLE_ADMIN,
    ROLE_OWNER,
    ROLE_USER,
    active_admin_users,
    authenticate_user,
    create_user,
    load_users,
    set_user_password,
    save_remembered_user,
    load_remembered_user,
    clear_remembered_user,
    update_user,
)


class AppUsersTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.users_path = Path(self.temp_dir.name) / "users.local.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_first_user_becomes_owner_and_can_login(self):
        user = create_user("dedeshko", "pass123", role=ROLE_USER, path=self.users_path)

        self.assertEqual(user["login"], "dedeshko")
        self.assertEqual(user["role"], ROLE_OWNER)
        self.assertNotIn("password_hash", user)

        logged_in = authenticate_user("dedeshko", "pass123", path=self.users_path)
        self.assertIsNotNone(logged_in)
        self.assertEqual(logged_in["role"], ROLE_OWNER)

    def test_wrong_password_is_rejected(self):
        create_user("dedeshko", "pass123", path=self.users_path)

        self.assertIsNone(authenticate_user("dedeshko", "wrong", path=self.users_path))

    def test_multiple_admins_are_allowed(self):
        create_user("owner", "pass123", path=self.users_path)
        create_user("admin2", "pass123", role=ROLE_ADMIN, path=self.users_path)

        data = load_users(self.users_path)
        self.assertEqual(len(active_admin_users(data)), 2)

    def test_last_admin_cannot_be_deactivated(self):
        create_user("owner", "pass123", path=self.users_path)

        with self.assertRaises(ValueError):
            update_user("owner", active=False, path=self.users_path)

    def test_last_admin_cannot_be_demoted(self):
        create_user("owner", "pass123", path=self.users_path)

        with self.assertRaises(ValueError):
            update_user("owner", role=ROLE_USER, path=self.users_path)

    def test_admin_can_be_demoted_when_another_admin_exists(self):
        create_user("owner", "pass123", path=self.users_path)
        create_user("admin2", "pass123", role=ROLE_ADMIN, path=self.users_path)

        updated = update_user("admin2", role=ROLE_USER, path=self.users_path)

        self.assertEqual(updated["role"], ROLE_USER)

    def test_duplicate_login_is_rejected_case_insensitive(self):
        create_user("Dedeshko", "pass123", path=self.users_path)

        with self.assertRaises(ValueError):
            create_user("dedeshko", "pass123", path=self.users_path)

    def test_password_can_be_changed(self):
        create_user("owner", "pass123", path=self.users_path)

        set_user_password("owner", "newpass", path=self.users_path)

        self.assertIsNone(authenticate_user("owner", "pass123", path=self.users_path))
        self.assertIsNotNone(authenticate_user("owner", "newpass", path=self.users_path))

    def test_remembered_user_can_be_loaded(self):
        create_user("owner", "pass123", path=self.users_path)
        remember_path = Path(self.temp_dir.name) / "remember.local.json"

        save_remembered_user("owner", path=self.users_path, remember_path=remember_path)
        remembered = load_remembered_user(path=self.users_path, remember_path=remember_path)

        self.assertIsNotNone(remembered)
        self.assertEqual(remembered["login"], "owner")
        self.assertNotIn("remember_token_hash", remembered)

    def test_remembered_user_is_invalidated_after_password_change(self):
        create_user("owner", "pass123", path=self.users_path)
        remember_path = Path(self.temp_dir.name) / "remember.local.json"

        save_remembered_user("owner", path=self.users_path, remember_path=remember_path)
        set_user_password("owner", "newpass", path=self.users_path)

        self.assertIsNone(load_remembered_user(path=self.users_path, remember_path=remember_path))

    def test_remembered_user_can_be_cleared(self):
        create_user("owner", "pass123", path=self.users_path)
        remember_path = Path(self.temp_dir.name) / "remember.local.json"

        save_remembered_user("owner", path=self.users_path, remember_path=remember_path)
        clear_remembered_user(remember_path=remember_path)

        self.assertIsNone(load_remembered_user(path=self.users_path, remember_path=remember_path))


if __name__ == "__main__":
    unittest.main()
