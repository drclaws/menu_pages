"""Tests of `build.py links`: the address of every page, for local use only."""

import unittest

from tests import fixtures, support

URL = "https://example.org/menu"

REFUSED_IN_CI = (
    "error: this command prints personal data and is meant for local use only; it does not run in CI "
    "(CI or GITHUB_ACTIONS is set)\nlinks: failed\n"
)


def expected_lines(guests: list, url: str = URL) -> list[str]:
    """What `links` prints for `guests`: the guests in order, the staff last."""
    lines = [f"{' '.join(record['name'].split())}\t{url}/{record['token']}/"
             for record in guests if record.get("staff") is not True]
    lines += [f"staff\t{url}/{record['token']}/" for record in guests if record.get("staff") is True]
    return lines


class LinksTest(support.TempDirTestCase):
    def write(self, menu: dict, guests: list, name: str = "data"):
        return fixtures.write_data(self.tmp / name, menu, guests)

    def test_a_line_per_guest_record_then_the_staff_page(self):
        for name, make in fixtures.SETS.items():
            with self.subTest(fixture=name):
                menu, guests = make()
                data = self.write(menu, guests, name)
                result = support.run_main("links", "--url", URL + "/", "--data", data)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.splitlines(), expected_lines(guests))
                self.assertTrue(result.stdout.splitlines()[-1].startswith("staff\t"))
                self.assertNoPrivateData(result.stderr, fixtures.tokens(guests), fixtures.names(guests, menu))

    def test_the_staff_record_may_come_first_in_the_file(self):
        menu, guests = fixtures.plain()
        guests.insert(0, guests.pop())
        result = support.run_main("links", "--url", URL, "--data", self.write(menu, guests))
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(lines, expected_lines(guests))
        self.assertEqual([line.split("\t")[0] for line in lines], [record["name"] for record in guests[1:]] + ["staff"])

    def test_the_white_space_of_a_name_is_collapsed(self):
        menu, guests = fixtures.plain()
        guests[0]["name"] = "Ezra   of the  Coast"
        result = support.run_main("links", "--url", URL, "--data", self.write(menu, guests))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[0], f"Ezra of the Coast\t{URL}/{guests[0]['token']}/")

    def test_without_a_staff_record_there_is_no_staff_line(self):
        menu, guests = fixtures.plain()
        del guests[-1]
        result = support.run_main("links", "--url", URL, "--data", self.write(menu, guests))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), expected_lines(guests))
        self.assertIn("no staff page is built", result.stderr)

    def test_broken_data_prints_no_line(self):
        menu, guests = fixtures.reserved19()
        guests[3]["seats"][0]["number"] = 4
        result = support.run_main("links", "--url", URL, "--data", self.write(menu, guests))
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr.splitlines()[-1], "links: failed with 1 error(s)")
        self.assertNoPrivateData(result.stderr, fixtures.tokens(guests), fixtures.names(guests, menu))

    def test_refused_in_ci(self):
        data = self.write(*fixtures.plain())
        for env in ({"CI": "true"}, {"GITHUB_ACTIONS": "true"}, {"CI": "1", "GITHUB_ACTIONS": ""}):
            with self.subTest(env=env):
                result = support.run_main("links", "--url", URL, "--data", data, env=env)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr, REFUSED_IN_CI)
        # an empty, 0 or false value is not CI
        result = support.run_main("links", "--url", URL, "--data", data, env={"CI": "false"})
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_refused_in_ci_before_the_data_is_read(self):
        result = support.run_main("links", "--url", URL, "--data", self.tmp / "nowhere", env={"CI": "true"})
        self.assertEqual((result.returncode, result.stdout, result.stderr), (1, "", REFUSED_IN_CI))

    def test_a_bad_url_is_a_usage_error_that_does_not_repeat_it(self):
        data = self.write(*fixtures.plain())
        for url in ("ftp://bjarne.example.org/menu", "https://judy:secret@example.org/menu",
                    "https://example.org/menu?wendell=1", "https://example.org/menu#rosalind",
                    "example.org/leopold", "https://%40example.org/menu"):
            with self.subTest(url=url):
                result = support.run_main("links", "--url", url, "--data", data)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("build.py links: error: argument --url: expected the address", result.stderr)
                self.assertNotIn(url, result.stderr)
                for word in ("bjarne", "judy", "secret", "wendell", "rosalind", "leopold", "%40"):
                    self.assertNotIn(word, result.stderr)

    def test_the_url_is_required(self):
        result = support.run_main("links", "--data", self.tmp)
        self.assertEqual(result.returncode, 2)
        self.assertIn("the following arguments are required: --url", result.stderr)

    def test_as_a_script(self):
        menu, guests = fixtures.reserved19()
        data = self.write(menu, guests)
        result = support.run_script("links", "--url", URL, "--data", data, cwd=self.tmp)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), expected_lines(guests))
        refused = support.run_script("links", "--url", URL, "--data", data, cwd=self.tmp, env={"CI": "true"})
        self.assertEqual((refused.returncode, refused.stdout, refused.stderr), (1, "", REFUSED_IN_CI))


if __name__ == "__main__":
    unittest.main()
