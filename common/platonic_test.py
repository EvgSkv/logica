#!/usr/bin/python
#
# Copyright 2023 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Unitests for platonic.py."""

from common.platonic import *
import unittest


class PlatonicTest(unittest.TestCase):
  def test_AdherenceSuccess(self):
    t1 = PlatonicObject({'a': Num})
    self.assertEqual(
        t1.AdheredBy({'a': 1}).Elements(), ({'a': 1}, True, None))

    t2 = PlatonicObject(
        {'a': Num,
         'aa': PlatonicObject({'b': Str,
                              'c': PlatonicObject({'d': Str})})})
    x2 = {'a': 1.0, 'aa': {'b': 'Seattle', 'c': {'d': 'Washington'}}}
    self.assertEqual(
        t2.AdheredBy(x2).Elements(), (x2, True, None))

    t3 = PlatonicObject(
        {'a': [Num], 'b': PlatonicObject({'c': [PlatonicObject({'d': Num})]})}
    )
    x3 = {'a': [1], 'b': {'c': [{'d': 5}]}}
    self.assertEqual(
        t3.AdheredBy(x3).Elements(), (x3, True, None))

  def test_AdherenceFailure(self):
    t1 = PlatonicObject({'a': Str})
    x1 = {'a': 1}
    self.assertEqual(
        t1.AdheredBy(x1).Elements(),
        (1, False, "{'a': 1}.a: Expected str, got 1"))

    t2 = PlatonicObject(
        {'a': Num,
         'aa': PlatonicObject({'b': Str,
                               'c': PlatonicObject({'d': Str})})})
    x2 = {'a': 1.0, 'aa': {'b': 5, 'c': {'d': 'Washington'}}}
    self.assertEqual(
        t2.AdheredBy(x2).Elements(),
        (5, False,
         "{'a': 1.0, 'aa': {'b': 5, 'c': {'d': " +
         "'Washington'}}}.aa.b: Expected str, got 5"))

    t3 = PlatonicObject(
        {'a': [Num], 'b': PlatonicObject({'c': [PlatonicObject({'d': Num})]})}
    )
    x3 = {'a': [1], 'b': {'c': {'d': 5}}}
    self.assertEqual(
        t3.AdheredBy(x3).Elements(),
        ({'c': {'d': 5}}, False, 
         "Record {'a': [1], 'b': {'c': {'d': 5}}}, " +
         "at path: .b encountered error: " +
         "Field value c was expected to be a list, got: {'d': 5}."))

    t4 = PlatonicObject({'a': PlatonicObject({'b': 1})})
    x4 = {'a': 5}
    self.assertEqual(t4.AdheredBy(x4).Elements(),
                     (5, False, 
                      "Record {'a': 5}, at path: .a encountered error:" +
                      " Expected record, but got not a dictionary."))
  
  def test_CheckPasses(self):
    t1 = PlatonicObject({'a': Str})
    x1 = {'a': 'earth'}
    self.assertEqual(t1(x1), x1)

  def test_CheckFails(self):
    t1 = PlatonicObject({'a': Str})
    x1 = {'a': 42}
    with self.assertRaises(AssertionError):
      t1(x1)