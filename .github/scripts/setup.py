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


import setuptools

version = "1.3.1415926535897"

with open("logica/README.md", "r") as f:
  long_description = f.read()

setuptools.setup(
  name = "logica",
  version = version,
  author = "Evgeny Skvortsov",
  author_email = "logica@evgeny.ninja",
  description = "Logica language.",
  long_description = long_description,
  long_description_content_type = "text/markdown",
  url="https://github.com/evgskv/logica",
  packages=setuptools.find_namespace_packages(),
  classifiers = [
      "Topic :: Database",
      "License :: OSI Approved :: Apache Software License"
  ],
  entry_points = {
    'console_scripts': ['logica=logica.logica:run_main']
  },
  python_requires= ">=3.0"
)
