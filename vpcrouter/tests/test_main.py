"""
Copyright 2017 Pani Networks Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

"""

#
# Unit tests for the main module
#

import sys
import unittest

from StringIO import StringIO

import vpcrouter.main as main

from vpcrouter.errors import ArgsError


class TestArgs(unittest.TestCase):
    """
    Tests argument parsing.

    These tests are bit funny, since they capture stdout.

    """
    def setUp(self):
        self.saved_stdout = sys.stdout
        self.saved_stderr = sys.stderr
        self.addCleanup(self.cleanup)

    def cleanup(self):
        sys.stdout = self.saved_stdout
        sys.stderr = self.saved_stderr

    def get_last_line(self, lines):
        return lines.split("\n")[-1]

    def prnt(self, text):
        # Allows me to print something to stdout during development
        self.saved_stdout.write(text + "\n")

    def test_parse_args(self):
        inp = [
            {"args" : ['-h'],
             "exc" : SystemExit, "out" : "0"},
            {"args" : ['-l'],
             "exc" : SystemExit, "out" : "2"},
            {"args" : ['-l', 'foo'],
             "exc" : SystemExit, "out" : "2"},
            {"args" : ['-l', 'foo', '-v', '123'],
             "exc" : None,
             "conf" : {
                 'verbose': False, 'addr': 'localhost', 'mode': 'http',
                 'file': None, 'vpc_id': '123', 'logfile': 'foo',
                 'port': 33289, 'region_name': 'ap-southeast-2'}},
            {"args" : ['-l', 'foo', '-v', '123', '-m', 'foo'],
             "exc" : ArgsError, "out" : "Invalid operating mode 'foo'."},
            {"args" : ['-l', 'foo', '-v', '123', '-m', 'conffile'],
             "exc" : ArgsError,
             "out" : "A config file needs to be specified (-f)."},
            {"args" : ['-l', 'foo', '-v', '123', '-m', 'conffile',
                       '-f', "/_does_not_exists"],
             "exc" : ArgsError,
             "out" : "Cannot open config file"},
            {"args" : ['-l', 'foo', '-v', '123', '-m', 'http', '-p', '99999'],
             "exc" : ArgsError,
             "out" : "Invalid listen port"},
            {"args" : ['-l', 'foo', '-v', '123', '-m', 'http', '-a', '999.9'],
             "exc" : ArgsError,
             "out" : "Not a valid IP address"}
        ]

        for i in inp:
            sys.stdout = StringIO()
            sys.stderr = StringIO()
            args = i['args']
            exc  = i['exc']
            out  = i.get('out', "")
            conf = i.get('conf', {})
            if exc:
                with self.assertRaises(exc) as ex:
                    main.parse_args(args)
                self.assertTrue(out in str(ex.exception.message))
            else:
                conf_is = main.parse_args(args)
                output = sys.stderr.getvalue().strip()
                ll     = self.get_last_line(output)
                if not out:
                    self.assertFalse(ll)
                else:
                    self.assertTrue(out in ll)
                if conf:
                    self.assertEqual(conf, conf_is)


if __name__ == '__main__':
    unittest.main()
