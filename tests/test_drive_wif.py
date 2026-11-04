import unittest
from scripts.drive_wif import choose_latest, list_folder_files

class DriveWifTests(unittest.TestCase):
    def test_latest_name_wins(self):
        files = [
            {'name': 'clinux_2026-10-31_13-15_root.sql', 'id':'b'},
            {'name': 'clinux_2026-10-31_10-13_root.sql', 'id':'a'},
            {'name': 'clinux_2026-09-30_19-20_root.sql', 'id':'c', 'modifiedTime':'2026-11-01T00:00:00Z'},
        ]
        self.assertEqual(choose_latest(files)['id'], 'b')

    def test_no_sql_rejected(self):
        with self.assertRaises(ValueError):
            choose_latest([{'name':'manual.txt'}])

    def test_reject_invalid_folder_id(self):
        with self.assertRaises(ValueError):
            list_folder_files(None, 'x\' or true')

if __name__ == '__main__':
    unittest.main()
