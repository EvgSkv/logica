#!/usr/bin/python
#
# Copyright 2020 Google LLC
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

"""Terminal text color string constants."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

CHR_ERROR = '\033[91m'
CHR_WARNING = '\033[1m'
# TODO: Make dark terminal users be able to configure to use the
# bright yellow.
# CHR_WARNING = '\033[93m'
CHR_UNDERLINE = '\033[4m'
CHR_END = '\033[0m'
CHR_OK = '\033[92m'


def Warn(message):
  return CHR_WARNING + message + CHR_END


def Color(color):
  return ColorsMap()[color]


def ColorsMap():
  return  {'error': CHR_ERROR,
           'warning': CHR_WARNING,
           'underline': CHR_UNDERLINE,
           'ok': CHR_OK,
           'end': CHR_END}


def Format(pattern, args_dict=None):
  args_dict = args_dict or {}
  return pattern.format(**dict(args_dict, **ColorsMap()))
