"""Offline source optimization regressions; never perform network requests."""
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from radar.database import RadarDB, job_fp
from radar.v2 import collect
from radar.matching import evaluate
from search.rss_search import SearchResult

ROOT = Path(__file__).resolve().parents[1]


def vacancy(title, ident):
    return SearchResult(
        title=title, url=f"https://jobs.ashbyhq.com/fake/{ident}",
        description="Figma", company="Test", source="Ashby · Test", source_kind="ats",
        provider="ashby", location="Remote - India",
        apply_url=f"https://jobs.ashbyhq.com/fake/{ident}",
        external_id=f"ashby:fake:{ident}",
    )


class SourceOptimizationTests(unittest.TestCase):
    def test_enabled_company_feeds_have_verified_public_board_slugs(self):
        config = json.loads((ROOT / 'config/company_watchlist.json').read_text())
        enabled = {b['company']: b for b in config['boards'] if b.get('enabled', True)}
        self.assertIn('PlayPower Labs', enabled)
        self.assertEqual(enabled['BJAK']['token'], 'bjakcareer')
        self.assertEqual(enabled['Tempo Labs']['token'], 'tempo')
        self.assertFalse(next(b for b in config['boards'] if b['company'] == 'e.l.f. Beauty')['enabled'])
        tokens = [(b['provider'], b['token']) for b in config['boards']]
        self.assertEqual(len(tokens), len(set(tokens)))

    def test_prefilter_removes_unrelated_roles_without_impacting_full_board_ids(self):
        all_jobs = [
            vacancy('UI/UX Designer', '1'),
            vacancy('Associate Product Designer', '2'),
            vacancy('Graphic Designer', '3'),
            vacancy('Product Manager', '4'),
            vacancy('Senior Product Designer', '5'),
        ]
        db = RadarDB(':memory:')
        try:
            board = {'provider':'ashby', 'company':'Test', 'token':'fake'}
            with patch('radar.v2.fetch_board', return_value=all_jobs), patch.dict(os.environ, {'PLATFORM_RSS_ENABLED':'0','ATS_TITLE_PREFILTER':'1'}):
                found, total, fails, successful = collect(
                    db, [board], rss_enabled=False, dry=True,
                    preferred_roles=['ui/ux designer','product designer'])
            self.assertEqual((total, fails), (1, 0))
            self.assertEqual({j.title for j in found}, {
                'UI/UX Designer', 'Associate Product Designer', 'Senior Product Designer'})
            self.assertEqual(set(successful[0][1]), {job_fp(j) for j in all_jobs})
        finally:
            db.close()

    def test_prefilter_does_not_change_legacy_callers_or_overrule_opt_out(self):
        jobs = [vacancy('Graphic Designer','1'), vacancy('UI Designer','2')]
        db = RadarDB(':memory:')
        try:
            board = {'provider':'ashby', 'company':'Test', 'token':'fake'}
            with patch('radar.v2.fetch_board', return_value=jobs), patch.dict(os.environ, {'PLATFORM_RSS_ENABLED':'0'}):
                found, _, _, _ = collect(db, [board], rss_enabled=False, dry=True)
                self.assertEqual(len(found), 2)
            with patch('radar.v2.fetch_board', return_value=jobs), patch.dict(os.environ, {'PLATFORM_RSS_ENABLED':'0','ATS_TITLE_PREFILTER':'0'}):
                found, _, _, _ = collect(db, [board], rss_enabled=False, dry=True, preferred_roles=['ui designer'])
                self.assertEqual(len(found), 2)
        finally:
            db.close()

    def test_employer_wording_this_role_is_remote_with_india_location(self):
        profile = json.loads((ROOT / 'config/profile.json').read_text())
        keywords = json.loads((ROOT / 'config/keywords.json').read_text())
        bjak = vacancy('Product Designer (UI/UX)', 'bjak')
        bjak.company = 'BJAK'
        bjak.location = 'India'
        bjak.description = '3+ years of experience in digital products. This role is remote, but candidates must be based in India.'
        outcome = evaluate(bjak, profile, keywords)
        self.assertTrue(outcome.accepted, outcome.rejection)
        self.assertGreaterEqual(outcome.score, 65)
        # Neither India alone nor generic references to remote colleagues suffice.
        bjak.description = 'Collaborate with remote teams. Must be based in India.'
        self.assertFalse(evaluate(bjak, profile, keywords).accepted)

    def test_manual_pages_not_in_automated_ats_list(self):
        manual = json.loads((ROOT / 'config/manual_career_pages.json').read_text())
        ats = json.loads((ROOT / 'config/company_watchlist.json').read_text())
        self.assertGreaterEqual(len(manual['pages']), 4)
        self.assertTrue(all(x['url'].startswith('https://') for x in manual['pages']))
        self.assertTrue(all(x.get('provider') != 'manual' for x in ats['boards']))
