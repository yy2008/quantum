# vim: tabstop=4 shiftwidth=4 softtabstop=4
#
# Copyright 2012 New Dream Network, LLC (DreamHost)
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

# @author Mark McClain (DreamHost)

import sys

import mock
import unittest2 as unittest

from quantum.db import migration
from quantum.db.migration import cli


class TestDbMigration(unittest.TestCase):
    def test_should_run_plugin_in_list(self):
        self.assertTrue(migration.should_run('foo', ['foo', 'bar']))
        self.assertFalse(migration.should_run('foo', ['bar']))

    def test_should_run_plugin_wildcard(self):
        self.assertTrue(migration.should_run('foo', ['*']))


class TestCli(unittest.TestCase):
    def setUp(self):
        self.do_alembic_cmd_p = mock.patch.object(cli, 'do_alembic_command')
        self.do_alembic_cmd = self.do_alembic_cmd_p.start()

    def tearDown(self):
        self.do_alembic_cmd_p.stop()
        cli.CONF.reset()

    def _main_test_helper(self, argv, func_name, exp_args=(), exp_kwargs={}):
        with mock.patch.object(sys, 'argv', argv):
            cli.main()
            self.do_alembic_cmd.assert_has_calls(
                [mock.call(mock.ANY, func_name, *exp_args, **exp_kwargs)]
            )

    def test_stamp(self):
        self._main_test_helper(
            ['prog', 'stamp', 'foo'],
            'stamp',
            ('foo',),
            {'sql': False}
        )

        self._main_test_helper(
            ['prog', 'stamp', 'foo', '--sql'],
            'stamp',
            ('foo',),
            {'sql': True}
        )

    def test_current(self):
        self._main_test_helper(['prog', 'current'], 'current')

    def test_history(self):
        self._main_test_helper(['prog', 'history'], 'history')

    def test_check_migration(self):
        self._main_test_helper(['prog', 'check_migration'], 'branches')

    def test_database_sync_revision(self):
        self._main_test_helper(
            ['prog', 'revision', '--autogenerate', '-m', 'message'],
            'revision',
            (),
            {'message': 'message', 'sql': False, 'autogenerate': True}
        )

        self._main_test_helper(
            ['prog', 'revision', '--sql', '-m', 'message'],
            'revision',
            (),
            {'message': 'message', 'sql': True, 'autogenerate': False}
        )

    def test_upgrade(self):
        self._main_test_helper(
            ['prog', 'upgrade', '--sql', 'head'],
            'upgrade',
            ('head',),
            {'sql': True}
        )

        self._main_test_helper(
            ['prog', 'upgrade', '--delta', '3'],
            'upgrade',
            ('+3',),
            {'sql': False}
        )

    def test_downgrade(self):
        self._main_test_helper(
            ['prog', 'downgrade', '--sql', 'folsom'],
            'downgrade',
            ('folsom',),
            {'sql': True}
        )

        self._main_test_helper(
            ['prog', 'downgrade', '--delta', '2'],
            'downgrade',
            ('-2',),
            {'sql': False}
        )
